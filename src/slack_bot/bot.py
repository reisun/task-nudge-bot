"""Slack Bot — SocketMode接続、タスク投稿、スレッド内AI応答."""

import logging
import os
import re
import threading

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.nudge.nudge import generate_nudge, generate_notification
from src.ticktick.client import TickTickClient, _parse_due_date_jst
from src.ticktick.habits import get_habits, checkin_habit

logger = logging.getLogger(__name__)

# グローバル参照（main.pyから設定される）
ticktick_client: TickTickClient | None = None

# botが投稿したメッセージのtsを記録（スレッド判定用）
_bot_message_timestamps: set[str] = set()

# TickTick再認証待ちスレッド
_auth_pending_thread: str | None = None

# タスクコンテキスト（カテゴリ別）
_categorized_tasks: dict[str, list[dict]] = {}
# 全タスクのフラットリスト（完了・検索用）
_all_tasks: list[dict] = []

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# 定時通知で表示するカテゴリ順（期限未設定は除外）
_NOTIFY_ORDER = ["overdue", "today", "week"]
# Claude向け会話コンテキストで表示するカテゴリ順
_CONTEXT_ORDER = ["overdue", "today", "week", "no_date"]


def post_tasks(categorized: dict[str, list[dict]],
               completed: list[dict] | None = None,
               habits: list[dict] | None = None) -> str | None:
    """カテゴリ別タスク一覧をClaudeで整形してSlackチャンネルに投稿."""
    global _categorized_tasks, _all_tasks
    _categorized_tasks = categorized
    _all_tasks = [t for cat in _CONTEXT_ORDER for t in categorized.get(cat, [])]
    channel = os.environ["SLACK_CHANNEL_ID"]

    # 通知対象タスク（期限付きのみ）
    notify_tasks = [t for cat in _NOTIFY_ORDER for t in categorized.get(cat, [])]

    # Claudeに整形させる
    tasks_context = _format_categorized(categorized, _NOTIFY_ORDER)
    if completed:
        completed_lines = "\n\n【今日完了したタスク】"
        for t in completed:
            completed_lines += f"\n• {t.get('title', '(no title)')}"
        tasks_context += completed_lines
    if habits:
        tasks_context += _format_habits(habits)
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
            due_str = _parse_due_date_jst(due).isoformat() if due else ""
            lines.append(f"• {t.get('title', '(no title)')} (期限: {due_str})")
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

    msg_ts = event.get("ts")
    THINKING_EMOJI = "thinking_face"

    # --- 認証コード受付 ---
    global _auth_pending_thread
    if _auth_pending_thread and thread_ts == _auth_pending_thread:
        code = user_text.strip()
        if code and not code.startswith("http"):
            try:
                ticktick_client.exchange_code(code)
                # タスクキャッシュをクリアして再取得を促す
                global _all_tasks, _categorized_tasks, _task_fetch_error
                _all_tasks = []
                _categorized_tasks = {}
                _task_fetch_error = None
                _auth_pending_thread = None
                say("認証が完了しました！タスクを取得できるようになりました :tada:", thread_ts=thread_ts)
            except Exception:
                logger.exception("Token exchange failed")
                say("認証コードが無効か期限切れのようです。もう一度認証URLを開いてやり直してみてください。", thread_ts=thread_ts)
            return

    # --- スレッド返信 ---
    if thread_ts and thread_ts in _bot_message_timestamps:
        threading.Thread(
            target=_respond_with_progress,
            args=(channel, thread_ts, user_text),
            daemon=True,
        ).start()
        return

    # --- チャンネルへの直接メッセージ ---
    if thread_ts:
        return  # bot以外のスレッドには反応しない

    threading.Thread(
        target=_respond_with_progress,
        args=(channel, None, user_text),
        daemon=True,
    ).start()


def _respond_with_progress(channel: str, thread_ts: str | None, user_text: str):
    """バックグラウンドでClaude応答を生成し、進捗をメッセージ編集で表示."""
    # 仮メッセージを投稿
    kwargs = {"channel": channel, "text": ":thinking_face: 考え中..."}
    if thread_ts:
        kwargs["thread_ts"] = thread_ts
    resp = app.client.chat_postMessage(**kwargs)
    status_ts = resp.get("ts", "")

    def on_progress(elapsed_sec: int):
        elapsed_min = elapsed_sec // 60
        elapsed_remaining = elapsed_sec % 60
        if elapsed_min > 0:
            time_str = f"{elapsed_min}分{elapsed_remaining}秒"
        else:
            time_str = f"{elapsed_sec}秒"
        try:
            app.client.chat_update(
                channel=channel, ts=status_ts,
                text=f":thinking_face: 考え中... ({time_str}経過)",
            )
        except Exception:
            logger.warning("Failed to update progress message", exc_info=True)

    tasks_context = _format_tasks_context()
    try:
        reply = generate_nudge(user_text, tasks_context, on_progress=on_progress)
    except Exception:
        logger.exception("AI nudge generation failed")
        reply = "ちょっとエラーが起きちゃった :sweat_smile: もう一度試してみて！"

    # **AUTH_NEEDED** マーカーを検出して認証URLを投稿
    if "**AUTH_NEEDED**" in reply:
        global _auth_pending_thread
        reply = reply.replace("**AUTH_NEEDED**", "").strip()
        # 仮メッセージを最終応答に置き換え
        try:
            app.client.chat_update(channel=channel, ts=status_ts, text=reply or "(応答なし)")
        except Exception:
            logger.exception("Failed to update final message")
        if ticktick_client:
            auth_url = ticktick_client.get_auth_url()
            reply_target = thread_ts or status_ts
            resp = app.client.chat_postMessage(
                channel=channel,
                thread_ts=reply_target,
                text=f":key: 以下のURLをブラウザで開いて認証してください:\n{auth_url}\n\n認証後、リダイレクトされたURLの `code=` の値をこのスレッドに貼り付けてください。",
            )
            _auth_pending_thread = reply_target
        return

    # **DONE:タスク名** マーカーを検出して完了処理
    done_match = re.search(r"\*\*DONE:(.+?)\*\*", reply)
    if done_match:
        task_title = done_match.group(1).strip()
        reply = re.sub(r"\s*\*\*DONE:.+?\*\*", "", reply).strip()
        _process_completion(task_title, channel, thread_ts)

    # **HABIT:習慣名** マーカーを検出してチェックイン
    habit_match = re.search(r"\*\*HABIT:(.+?)\*\*", reply)
    if habit_match:
        habit_name = habit_match.group(1).strip()
        reply = re.sub(r"\s*\*\*HABIT:.+?\*\*", "", reply).strip()
        result = checkin_habit(habit_name)
        if result:
            logger.info("Checked in habit: %s", result)
        else:
            logger.warning("Failed to checkin habit: %s", habit_name)

    # 仮メッセージを最終応答に置き換え
    try:
        app.client.chat_update(channel=channel, ts=status_ts, text=reply or "(応答なし)")
    except Exception:
        logger.exception("Failed to update final message")


def _add_reaction(channel: str, timestamp: str, emoji: str) -> None:
    """メッセージにリアクション絵文字を付与."""
    try:
        app.client.reactions_add(channel=channel, timestamp=timestamp, name=emoji)
    except Exception:
        logger.warning("Failed to add reaction :%s:", emoji, exc_info=True)


def _remove_reaction(channel: str, timestamp: str, emoji: str) -> None:
    """メッセージからリアクション絵文字を除去."""
    try:
        app.client.reactions_remove(channel=channel, timestamp=timestamp, name=emoji)
    except Exception:
        logger.warning("Failed to remove reaction :%s:", emoji, exc_info=True)


def _process_completion(task_title: str, channel: str, thread_ts: str | None):
    """Claudeが特定したタスク名でTickTickのタスクを完了にする."""
    global _all_tasks, _categorized_tasks
    _refresh_tasks()
    if not ticktick_client or not _all_tasks:
        logger.warning("Cannot complete task: no tasks loaded")
        return

    target = _find_task(task_title)
    if not target:
        logger.warning("Task not found for completion: %s", task_title)
        return

    try:
        ticktick_client.complete_task(target["_project_id"], target["id"])
        logger.info("Completed task: %s", target["title"])
        # タスクキャッシュをクリアして次回再取得
        _all_tasks = []
        _categorized_tasks = {}
    except Exception:
        logger.exception("Failed to complete task: %s", task_title)


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


_task_fetch_error: str | None = None


def _refresh_tasks() -> None:
    """TickTickからタスクを再取得してキャッシュを更新."""
    global _categorized_tasks, _all_tasks, _task_fetch_error
    if ticktick_client and not _all_tasks:
        try:
            _categorized_tasks = ticktick_client.get_categorized_tasks()
            _all_tasks = [t for cat in _CONTEXT_ORDER for t in _categorized_tasks.get(cat, [])]
            _task_fetch_error = None
            logger.info("Refreshed tasks: %d found", len(_all_tasks))
        except Exception as e:
            logger.exception("Failed to refresh tasks")
            _task_fetch_error = str(e)


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
            if due:
                due_date = _parse_due_date_jst(due)
                due_suffix = f" (期限: {due_date.isoformat()})"
            else:
                due_suffix = ""
            lines.append(f"{idx}. {t.get('title', '(no title)')}{due_suffix}")
            idx += 1
    return "\n".join(lines)


def _format_tasks_context() -> str:
    """カテゴリ別タスクリストを文字列化（Claude向け会話コンテキスト）."""
    _refresh_tasks()
    if _task_fetch_error:
        context = f"【エラー】タスクの取得に失敗しました: {_task_fetch_error}"
    elif not _all_tasks:
        context = "タスクはありません。"
    else:
        context = _format_categorized(_categorized_tasks, _CONTEXT_ORDER)

    # 今日の完了タスクも追加
    if ticktick_client:
        try:
            completed = ticktick_client.get_todays_completed_tasks()
            if completed:
                context += "\n\n【今日完了したタスク】"
                for t in completed:
                    context += f"\n• {t.get('title', '(no title)')}"
        except Exception:
            logger.warning("Failed to fetch completed tasks for context", exc_info=True)

    # 習慣情報も追加
    try:
        habits = get_habits()
        if habits:
            context += _format_habits(habits)
    except Exception:
        logger.warning("Failed to fetch habits for context", exc_info=True)

    return context


def _format_habits(habits: list[dict]) -> str:
    """習慣リストを文字列化（チェック状態付き）."""
    lines = ["\n\n【習慣】"]
    for h in habits:
        checked = h.get("checked_today", False)
        mark = "✅" if checked else "⬜"
        lines.append(f"{mark} {h.get('name', '(no name)')}")
    return "\n".join(lines)


def start_socket_mode() -> SocketModeHandler:
    """SocketModeハンドラーを作成して返す."""
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    return handler
