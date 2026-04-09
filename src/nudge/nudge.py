"""AI Nudge — Claude CLIでナッジ応答を生成."""

import logging
import re
import subprocess
from datetime import datetime

from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _markdown_to_slack_mrkdwn(text: str) -> str:
    """Markdown記法をSlack mrkdwn形式に変換."""
    # **bold** → *bold*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    # __bold__ → *bold*
    text = re.sub(r"__(.+?)__", r"*\1*", text)
    # [text](url) → <url|text>
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)
    # ### heading → *heading*
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
    return text

SYSTEM_PROMPT = """\
あなたは生活支援botです。
タスク管理を通じて、ユーザーがより良い日常を送れるようサポートすることが目的です。
タスクの進捗を促すだけでなく、体調・気分・生活リズムにも気を配ってください。

ユーザーが話しかけてきたら、時間帯や状況に合わせて自然に応じてください。
優しく、でも具体的に「じゃあこれからやろうか」と促してください。
タスクの完了を報告されたら褒めてください。
日本語で、カジュアルな口調で応答してください。
応答は短めに（2-3文以内）。

あなたはTickTickと連携しており、ユーザーのタスク情報にアクセスできます。
「今日のタスク」セクションに現在のタスク一覧が含まれています。
タスクがない場合でも、ユーザーの質問や雑談には気軽に応じてください。
"""


NOTIFICATION_PROMPT = """\
あなたは生活支援botです。
以下のタスク一覧をSlackチャンネルに投稿するためのメッセージを作成してください。

ルール:
- Slack mrkdwn形式で書式を付けてください（*太字*、:emoji: など）
- カテゴリごとにまとめて、見やすく整理してください
- 時間帯に合わせた一言を添えてください（朝なら「おはよう」、夜なら「お疲れさま」など）
- タスクがなければ「タスクなし」で一言添えてください
- 日本語で、カジュアルな口調で
"""


def generate_nudge(user_message: str, tasks_context: str) -> str:
    """Claude CLIを呼び出してナッジ応答を生成.

    Args:
        user_message: ユーザーの入力テキスト
        tasks_context: 現在のタスク一覧（テキスト形式）

    Returns:
        AIからの応答テキスト
    """
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M")

    prompt = f"""\
## 現在時刻（日本時間）
{now}

## タスク一覧
{tasks_context}

## ユーザーの発言
{user_message}
"""

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "-p", prompt,
                "--system-prompt", SYSTEM_PROMPT,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            logger.error("Claude CLI error: %s", result.stderr)
            return "うまく考えがまとまらなかった… もう一回話してみて！"

        return _markdown_to_slack_mrkdwn(result.stdout.strip())

    except FileNotFoundError:
        logger.error("Claude CLI not found. Is it installed?")
        return "AI機能が使えない状態です。管理者に連絡してください。"
    except subprocess.TimeoutExpired:
        logger.error("Claude CLI timed out")
        return "考えるのに時間がかかりすぎちゃった :hourglass: もう一度試してね。"


def generate_notification(tasks_context: str) -> str:
    """定時通知用のメッセージをClaudeに生成させる."""
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M")

    prompt = f"""\
## 現在時刻（日本時間）
{now}

## タスク一覧
{tasks_context}
"""

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "-p", prompt,
                "--system-prompt", NOTIFICATION_PROMPT,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error("Claude CLI error: %s", result.stderr)
            return None

        return _markdown_to_slack_mrkdwn(result.stdout.strip())

    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.exception("Claude CLI failed for notification")
        return None
