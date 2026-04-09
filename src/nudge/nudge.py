"""AI Nudge — Claude CLIでナッジ応答を生成."""

import logging
import subprocess
import time
import threading
from datetime import datetime

from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
あなたは生活支援botです。
タスク管理を通じて、ユーザーがより良い日常を送れるようサポートすることが目的です。
タスクの進捗を促すだけでなく、体調・気分・生活リズムにも気を配ってください。
Slackチャンネルに投稿されるため書式に注意してください。

ユーザーが話しかけてきたら、時間帯や状況に合わせて自然に応じてください。
優しく、でも具体的に「じゃあこれからやろうか」と促してください。
日本語で、カジュアルな口調で応答してください。
応答は短めに（2-3文以内）。

あなたはTickTickと連携しており、ユーザーのタスク情報にアクセスできます。
「タスク一覧」セクションに現在のタスク一覧が含まれています。
タスクがない場合でも、ユーザーの質問や雑談には気軽に応じてください。

## タスク完了機能
ユーザーがタスクの完了を報告した場合（「〇〇終わった」「〇〇完了」「〇〇やった」など）、\
タスク一覧から該当するタスクを特定し、応答の末尾に以下のマーカーを付けてください:
**DONE:タスク名**

例: ユーザー「病院選定おわったよ」→ タスク一覧に「健康ドックの病院選定」がある場合
応答:「(一言添える)」
**DONE:健康ドックの病院選定**

タスク名はタスク一覧に記載されている正確なタスク名を使ってください。
該当タスクが特定できない場合はマーカーを付けず、どのタスクか確認してください。
"""


NOTIFICATION_PROMPT = """\
あなたは生活支援botです。
以下のルールでタスク一覧をユーザーに知らせてください。
Slackチャンネルに投稿されるため書式に注意してください。

ルール:
- Slack mrkdwn形式で書式を付けてください（*太字*、:emoji: など）
- カテゴリごとにまとめて、見やすく整理してください
- 時間帯に合わせた一言を添えてください（朝なら「おはよう」、夜なら「お疲れさま」など）
- 今日完了したタスクがあれば、盛り上げて褒めてください！達成感を感じられるように
- タスクがなければ「タスクなし」で一言添えてください
- 日本語で、カジュアルな口調で
"""


def generate_nudge(user_message: str, tasks_context: str,
                    on_progress=None) -> str:
    """Claude CLIを呼び出してナッジ応答を生成.

    Args:
        user_message: ユーザーの入力テキスト
        tasks_context: 現在のタスク一覧（テキスト形式）
        on_progress: コールバック on_progress(elapsed_sec) — 処理中に定期呼び出し

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
        proc = subprocess.Popen(
            [
                "claude",
                "--print",
                "-p", prompt,
                "--system-prompt", SYSTEM_PROMPT,
                "--allowedTools", "WebSearch", "WebFetch",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        start = time.monotonic()
        while proc.poll() is None:
            time.sleep(5)
            elapsed = int(time.monotonic() - start)
            if on_progress and elapsed >= 10:
                on_progress(elapsed)

        stdout = proc.stdout.read()
        stderr = proc.stderr.read()

        if proc.returncode != 0:
            logger.error("Claude CLI error: %s", stderr)
            return "うまく考えがまとまらなかった… もう一回話してみて！"

        return stdout.strip()

    except FileNotFoundError:
        logger.error("Claude CLI not found. Is it installed?")
        return "AI機能が使えない状態です。管理者に連絡してください。"


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

        return result.stdout.strip()

    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.exception("Claude CLI failed for notification")
        return None
