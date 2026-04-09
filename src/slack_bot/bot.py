"""Slack Bot — SocketMode接続、タスク投稿、スレッド内AI応答."""

import logging
import os
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.nudge.nudge import generate_nudge, generate_notification
from src.ticktick.client import TickTickClient

logger = logging.getLogger(__name__)

# グローバル参照（main.pyから設定される）
ticktick_client: TickTickClient | None = None

# botが投稿したメッセージのtsを記録（スレッド判定用）
_bot_message_timestamps: set[str] = set()

# タスクコンテキスト（カテゴリ別）
_categorized_tasks: dict[str, list[dict]] = {}
# 全タスクのフラットリスト（完了・検索用）
_all_tasks: list[dict] = []

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# 定時通知で表示するカテゴリ順（期限未設定は除外）
_NOTIFY_ORDER = ["overdue", "today", "week"]
# Claude向け会話コンテキストで表示するカテゴリ順
_CONTEXT_ORDER = ["overdue", "today", "week", "no_date"]


def post_tasks(categorized: dict[str, list[dict]]) -> str | None:
    """カテゴリ別タスク一覧をClaudeで整形してSlackチャンネルに投稿."""
    global _categorized_tasks, _all_tasks
    _categorized_tasks = categorized
    _all_tasks = [t for cat in _CONTEXT_ORDER for t in categorized.get(cat, [])]
    channel = os.environ["SLACK_CHANNEL_ID"]

    # 通知対象タスク（期限付きのみ）
    notify_tasks = [t for cat in _NOTIFY_ORDER for t in categorized.get(cat, [])]

    # Claudeに整形させる
    tasks_context = _format_categorized(categorized, _NOTIFY_ORDER)
    claude_text = generate_notification(tasks_context)

    if claude_text:
        text = f"<!channel>\n{claude_text}"
    elif not notify_tasks:
        text = "<!channel> 期限付きのタスクはありません :tada:"
    else:
        # フォールバック: Claude失敗時は簡易表示
        lines = ["<!channel> *タスク通知*\n"]
        for t in notify_tasks:
            due = t.get("dueDate", "")
            lines.append(f"• {t.get('title', '(no title)')} (期限: {due[:10]})")
        text = "\n".join(lines)

    resp = app.client.chat_postMessage(channel=channel, text=text)
    ts = resp.get("ts")
    if ts:
        _bot_message_timestamps.add(ts)
    return ts


@app.event("message")
def handle_message(event: dict, say) -> None:
    """チャンネルメッセージおよびスレッド内の返信を処理."""
    logger.info("handle_message called: channel=%s text=%s bot_id=%s subtype=%s",
                event.get("channel"), (event.get("text") or "")[:40],
                event.get("bot_id"), event.get("subtype"))
    # bot自身のメッセージは無視
    if event.get("bot_id") or event.get("subtype"):
        return

    channel = os.environ.get("SLACK_CHANNEL_ID", "")
    if event.get("channel") != channel:
        return

    user_text = event.get("text", "")
    thread_ts = event.get("thread_ts")

    # --- スレッド返信 ---
    if thread_ts and thread_ts in _bot_message_timestamps:
        # 「完了」パターンの検出
        if _handle_completion(user_text, thread_ts, say):
            return

        tasks_context = _format_tasks_context()
        try:
            reply = generate_nudge(user_text, tasks_context)
        except Exception:
            logger.exception("AI nudge generation failed")
            reply = "ちょっとエラーが起きちゃった :sweat_smile: もう一度試してみて！"

        say(text=reply, thread_ts=thread_ts)
        return

    # --- チャンネルへの直接メッセージ ---
    if thread_ts:
        return  # bot以外のスレッドには反応しない

    tasks_context = _format_tasks_context()
    try:
        reply = generate_nudge(user_text, tasks_context)
    except Exception:
        logger.exception("AI nudge generation failed")
        reply = "ちょっとエラーが起きちゃった :sweat_smile: もう一度試してみて！"

    say(text=reply)


def _handle_completion(user_text: str, thread_ts: str, say) -> bool:
    """「完了」メッセージを処理. 処理した場合Trueを返す."""
    # 「完了」「完了 タスク名」パターンを検出
    match = re.match(r"^完了\s*(.*)", user_text.strip())
    if not match:
        return False

    task_hint = match.group(1).strip()
    if not ticktick_client or not _all_tasks:
        say(text="タスク情報がまだ読み込まれていません。", thread_ts=thread_ts)
        return True

    # タスクを特定（名前の部分一致 or 番号指定）
    target = _find_task(task_hint)
    if not target:
        say(
            text=f"「{task_hint}」に該当するタスクが見つかりませんでした。タスク名の一部を入れてみてください。",
            thread_ts=thread_ts,
        )
        return True

    try:
        ticktick_client.complete_task(target["_project_id"], target["id"])
        say(
            text=f":white_check_mark: *{target['title']}* を完了にしました！お疲れさま！",
            thread_ts=thread_ts,
        )
    except Exception:
        logger.exception("Failed to complete task")
        say(text="タスクの完了処理でエラーが発生しました :bow:", thread_ts=thread_ts)

    return True


def _find_task(hint: str) -> dict | None:
    """ヒント文字列からタスクを検索."""
    if not hint:
        # ヒントなしで1つだけなら自動選択
        return _all_tasks[0] if len(_all_tasks) == 1 else None

    # 番号指定
    if hint.isdigit():
        idx = int(hint) - 1
        if 0 <= idx < len(_all_tasks):
            return _all_tasks[idx]

    # 名前の部分一致
    for task in _all_tasks:
        if hint.lower() in task.get("title", "").lower():
            return task

    return None


def _refresh_tasks() -> None:
    """TickTickからタスクを再取得してキャッシュを更新."""
    global _categorized_tasks, _all_tasks
    if ticktick_client and not _all_tasks:
        try:
            _categorized_tasks = ticktick_client.get_categorized_tasks()
            _all_tasks = [t for cat in _CONTEXT_ORDER for t in _categorized_tasks.get(cat, [])]
            logger.info("Refreshed tasks: %d found", len(_all_tasks))
        except Exception:
            logger.exception("Failed to refresh tasks")


def _format_categorized(categorized: dict[str, list[dict]], order: list[str]) -> str:
    """カテゴリ別タスクリストを文字列化."""
    label_map = {
        "overdue": "【期限切れ】",
        "today": "【今日】",
        "week": "【今週】",
        "no_date": "【期限未設定】",
    }
    lines = []
    idx = 1
    for cat_key in order:
        tasks = categorized.get(cat_key, [])
        if not tasks:
            continue
        lines.append(f"\n{label_map[cat_key]}")
        for t in tasks:
            due = t.get("dueDate", "")
            due_suffix = f" (期限: {due[:10]})" if due else ""
            lines.append(f"{idx}. {t.get('title', '(no title)')}{due_suffix}")
            idx += 1
    return "\n".join(lines)


def _format_tasks_context() -> str:
    """カテゴリ別タスクリストを文字列化（Claude向け会話コンテキスト）."""
    _refresh_tasks()
    if not _all_tasks:
        return "タスクはありません。"
    return _format_categorized(_categorized_tasks, _CONTEXT_ORDER)


def start_socket_mode() -> SocketModeHandler:
    """SocketModeハンドラーを作成して返す."""
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    return handler
