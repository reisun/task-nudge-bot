"""AI Nudge — Claude CLIでナッジ応答を生成."""

import logging
import subprocess

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
あなたはタスク管理のナッジbotです。
ユーザーが今日やるべきタスクについて話しています。
優しく、でも具体的に「じゃあこれからやろうか」と促してください。
タスクの完了を報告されたら褒めてください。
日本語で、カジュアルな口調で応答してください。
応答は短めに（2-3文以内）。
"""


def generate_nudge(user_message: str, tasks_context: str) -> str:
    """Claude CLIを呼び出してナッジ応答を生成.

    Args:
        user_message: ユーザーの入力テキスト
        tasks_context: 現在のタスク一覧（テキスト形式）

    Returns:
        AIからの応答テキスト
    """
    prompt = f"""\
## 今日のタスク
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
                "--system", SYSTEM_PROMPT,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error("Claude CLI error: %s", result.stderr)
            return "うまく考えがまとまらなかった… もう一回話してみて！"

        return result.stdout.strip()

    except FileNotFoundError:
        logger.error("Claude CLI not found. Is it installed?")
        return "AI機能が使えない状態です。管理者に連絡してください。"
    except subprocess.TimeoutExpired:
        logger.error("Claude CLI timed out")
        return "考えるのに時間がかかりすぎちゃった :hourglass: もう一度試してね。"
