"""AI Nudge — Agent Gateway経由でナッジ応答を生成."""

import logging
import os
import time

import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

AGENT_GATEWAY_URL = os.environ.get("AGENT_GATEWAY_URL", "http://llm-internal-proxy/agent")

SYSTEM_PROMPT = """\
あなたは生活支援botです。
タスク管理を通じて、ユーザーがより良い日常を送れるようサポートすることが目的です。
タスクの進捗を促すだけでなく、体調・気分・生活リズムにも気を配ってください。
Slackチャンネルに投稿されるため書式に注意してください。

ユーザーが話しかけてきたら、時間帯や状況に合わせて自然に応じてください。
優しく、でも具体的に「じゃあこれからやろうか」と促してください。
日本語で、カジュアルな口調で応答してください。
応答は短めに（2-3文以内）。

あなたはTickTickと連携しており、ユーザーのタスクと習慣の情報にアクセスできます。
コンテキストにタスク一覧と習慣一覧が含まれています。
「タスク教えて」等の一般的な質問にはタスクと習慣の両方を対象に答えてください。
タスクも習慣もない場合でも、ユーザーの質問や雑談には気軽に応じてください。

## TickTick認証エラーについて
コンテキストに「タスクの取得に失敗しました」というエラーが含まれている場合、\
TickTickのOAuth認証トークンが期限切れの可能性が高いです。
その場合は応答の末尾に以下のマーカーを付けてください:
**AUTH_NEEDED**

マーカーを付けると、システムが自動的に認証URLをユーザーに提示します。
応答本文ではタスク取得でエラーが起きていることと、再認証が必要なことを簡潔に伝えてください。
認証URLやコマンドを自分で書く必要はありません。

## タスク完了機能
ユーザーがタスクの完了を報告した場合（「〇〇終わった」「〇〇完了」「〇〇やった」など）、\
タスク一覧から該当するタスクを特定し、応答の末尾に以下のマーカーを付けてください:
**DONE:タスク名**

タスク名はタスク一覧に記載されている正確なタスク名を使ってください。

## 習慣チェックイン機能
ユーザーが習慣の実施を報告した場合も同様に、習慣一覧から特定し:
**HABIT:習慣名**

例: ユーザー「ダンベルやったよ」→ 習慣一覧に「ダンベル運動」がある場合
応答:「(一言添える)」
**HABIT:ダンベル運動**

習慣名は習慣一覧に記載されている正確な名前を使ってください。
該当が特定できない場合はマーカーを付けず、どれか確認してください。
タスクと習慣の両方に該当する場合は両方のマーカーを付けてください。
"""


NOTIFICATION_PROMPT = """\
あなたは生活支援botです。
以下のルールでタスク一覧をユーザーに知らせてください。
Slackチャンネルに投稿されるため書式に注意してください。

ルール:
- Slack mrkdwn形式で書式を付けてください（*太字*、:emoji: など）
- １行目は「定期タスク通知(MM/dd HH:mm)」で始めてください
- カテゴリごとにまとめて、見やすく整理してください
- 時間帯に合わせた一言を添えてください（朝なら「おはよう」、夜なら「お疲れさま」など）
- 今日完了したタスクがあれば、盛り上げて褒めてください！達成感を感じられるように
- 習慣があれば、今日やるべき習慣としてリマインドしてください
- タスクがなければ「タスクなし」で一言添えてください
- 日本語で、カジュアルな口調で
"""


_POLL_INTERVAL = 5
_DEFAULT_TIMEOUT = 300


def _submit_job(prompt: str, system_prompt: str, timeout: int = _DEFAULT_TIMEOUT) -> str | None:
    """Agent Gateway にジョブを投入し job_id を返す."""
    payload = {
        "agent": "claude",
        "prompt": prompt,
        "model": "sonnet",
        "system_prompt": system_prompt,
        "timeout": timeout,
        "permissions": "readonly",
    }
    try:
        resp = httpx.post(f"{AGENT_GATEWAY_URL}/run", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["job_id"]
    except (httpx.HTTPError, KeyError) as e:
        logger.error("Agent Gateway submit failed: %s", e)
        return None


def _poll_job(job_id: str, timeout: int = _DEFAULT_TIMEOUT,
              on_progress=None) -> str | None:
    """ジョブ完了までポーリングし結果を返す."""
    start = time.monotonic()
    while True:
        elapsed = int(time.monotonic() - start)
        if elapsed > timeout + 30:
            logger.error("Agent Gateway polling timed out for job %s", job_id)
            return None

        if on_progress and elapsed >= 10:
            on_progress(elapsed)

        try:
            resp = httpx.get(
                f"{AGENT_GATEWAY_URL}/jobs/{job_id}", timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.warning("Agent Gateway poll error: %s", e)
            time.sleep(_POLL_INTERVAL)
            continue

        status = data.get("status")
        if status == "done":
            return data.get("result", "").strip()
        elif status == "failed":
            logger.error("Agent Gateway job failed: %s", data.get("error"))
            return None
        elif status in ("queued", "running"):
            time.sleep(_POLL_INTERVAL)
        else:
            logger.warning("Unknown job status: %s", status)
            time.sleep(_POLL_INTERVAL)


def generate_nudge(user_message: str, tasks_context: str,
                    on_progress=None) -> str:
    """Agent Gateway経由でナッジ応答を生成.

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

    job_id = _submit_job(prompt, SYSTEM_PROMPT, timeout=_DEFAULT_TIMEOUT)
    if not job_id:
        return "うまく考えがまとまらなかった… もう一回話してみて！"

    result = _poll_job(job_id, timeout=_DEFAULT_TIMEOUT, on_progress=on_progress)
    if not result:
        return "うまく考えがまとまらなかった… もう一回話してみて！"

    return result


def generate_notification(tasks_context: str) -> str:
    """定時通知用のメッセージを生成させる."""
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M")

    prompt = f"""\
## 現在時刻（日本時間）
{now}

## タスク一覧
{tasks_context}
"""

    job_id = _submit_job(prompt, NOTIFICATION_PROMPT, timeout=120)
    if not job_id:
        return None

    result = _poll_job(job_id, timeout=120)
    return result
