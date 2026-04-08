"""Slack Bot — SocketMode接続、タスク投稿、スレッド内AI応答."""

import logging
import os
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.nudge.nudge import generate_nudge
from src.ticktick.client import TickTickClient

logger = logging.getLogger(__name__)

# グローバル参照（main.pyから設定される）
ticktick_client: TickTickClient | None = None

# botが投稿したメッセージのtsを記録（スレッド判定用）
_bot_message_timestamps: set[str] = set()

# タスクコンテキスト（最新の投稿タスクを保持）
_current_tasks: list[dict] = []

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))


def post_tasks(tasks: list[dict]) -> str | None:
    """今日のタスク一覧をSlackチャンネルに投稿. 投稿のtsを返す."""
    global _current_tasks
    _current_tasks = tasks
    channel = os.environ["SLACK_CHANNEL_ID"]

    if not tasks:
        text = "今日のタスクはありません :tada: ゆっくり休んでください！"
    else:
        lines = ["*今日のタスク* :memo:\n"]
        for i, task in enumerate(tasks, 1):
            project = task.get("_project_name", "")
            title = task.get("title", "(no title)")
            prefix = f"[{project}] " if project else ""
            lines.append(f"{i}. {prefix}{title}")
        lines.append("\nスレッドで話しかけてね！完了したら「完了 タスク名」と教えてください。")
        text = "\n".join(lines)

    resp = app.client.chat_postMessage(channel=channel, text=text)
    ts = resp.get("ts")
    if ts:
        _bot_message_timestamps.add(ts)
    return ts


@app.event("message")
def handle_message(event: dict, say) -> None:
    """スレッド内の返信を処理."""
    # スレッド返信のみ対象
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return

    # botが投稿したメッセージのスレッドのみ対応
    if thread_ts not in _bot_message_timestamps:
        return

    # bot自身のメッセージは無視
    if event.get("bot_id"):
        return

    user_text = event.get("text", "")

    # 「完了」パターンの検出
    if _handle_completion(user_text, thread_ts, say):
        return

    # AI Nudge応答
    tasks_context = _format_tasks_context()
    try:
        reply = generate_nudge(user_text, tasks_context)
    except Exception:
        logger.exception("AI nudge generation failed")
        reply = "ちょっとエラーが起きちゃった :sweat_smile: もう一度試してみて！"

    say(text=reply, thread_ts=thread_ts)


def _handle_completion(user_text: str, thread_ts: str, say) -> bool:
    """「完了」メッセージを処理. 処理した場合Trueを返す."""
    # 「完了」「完了 タスク名」パターンを検出
    match = re.match(r"^完了\s*(.*)", user_text.strip())
    if not match:
        return False

    task_hint = match.group(1).strip()
    if not ticktick_client or not _current_tasks:
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
        return _current_tasks[0] if len(_current_tasks) == 1 else None

    # 番号指定
    if hint.isdigit():
        idx = int(hint) - 1
        if 0 <= idx < len(_current_tasks):
            return _current_tasks[idx]

    # 名前の部分一致
    for task in _current_tasks:
        if hint.lower() in task.get("title", "").lower():
            return task

    return None


def _format_tasks_context() -> str:
    """現在のタスクリストを文字列化."""
    if not _current_tasks:
        return "タスクはありません。"
    lines = []
    for i, t in enumerate(_current_tasks, 1):
        lines.append(f"{i}. {t.get('title', '(no title)')}")
    return "\n".join(lines)


def start_socket_mode() -> SocketModeHandler:
    """SocketModeハンドラーを作成して返す."""
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    return handler
