"""TickTick Habits — V2 API経由で習慣情報を取得."""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ticktick_sdk import TickTickClient

JST = ZoneInfo("Asia/Tokyo")

# Python weekday (0=Mon) → RRULE BYDAY
_WEEKDAY_MAP = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

logger = logging.getLogger(__name__)

TOKEN_FILE = Path(os.environ.get("TOKEN_FILE", ".tokens.json"))


def _run_async(coro):
    """同期コンテキストからasyncを実行."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _get_v1_token() -> str | None:
    """V1 OAuthトークンをファイルから取得."""
    if TOKEN_FILE.exists():
        data = json.loads(TOKEN_FILE.read_text())
        return data.get("access_token")
    return None


def _is_today_habit(repeat_rule: str | None) -> bool:
    """RRULEのBYDAYに今日の曜日が含まれているか判定."""
    if not repeat_rule:
        return True  # ルールなしは毎日扱い
    today_byday = _WEEKDAY_MAP[datetime.now(JST).weekday()]
    byday_match = re.search(r"BYDAY=([A-Z,]+)", repeat_rule)
    if not byday_match:
        return True  # BYDAYなしは毎日扱い
    return today_byday in byday_match.group(1).split(",")


async def _fetch_habits() -> list[dict]:
    """V2 APIから今日の習慣一覧を取得（チェック状態付き）."""
    v1_token = _get_v1_token()
    client = TickTickClient(
        client_id=os.environ["TICKTICK_CLIENT_ID"],
        client_secret=os.environ["TICKTICK_CLIENT_SECRET"],
        username=os.environ.get("TICKTICK_USERNAME", ""),
        password=os.environ.get("TICKTICK_PASSWORD", ""),
        v1_access_token=v1_token,
    )
    try:
        await client.connect()
        habits = await client.get_all_habits()

        # 今日のチェックイン状態を取得
        today_stamp = int(datetime.now(JST).strftime("%Y%m%d"))
        habit_ids = [h.id for h in habits]
        checkins_dict = await client.get_habit_checkins(habit_ids) if habit_ids else {}

        result = []
        for h in habits:
            if not _is_today_habit(getattr(h, "repeat_rule", None)):
                continue
            checkins = checkins_dict.get(h.id, [])
            checked_today = any(c.checkin_stamp == today_stamp for c in checkins)
            result.append({
                "id": h.id,
                "name": h.name,
                "status": getattr(h, "status", None),
                "goal": getattr(h, "goal", None),
                "frequency": getattr(h, "frequency", None),
                "checked_today": checked_today,
            })
        return result
    finally:
        await client.disconnect()


def get_habits() -> list[dict]:
    """習慣一覧を同期的に取得."""
    if not os.environ.get("TICKTICK_USERNAME") or not os.environ.get("TICKTICK_PASSWORD"):
        logger.info("TickTick V2 credentials not set, skipping habits")
        return []
    try:
        return _run_async(_fetch_habits())
    except Exception:
        logger.exception("Failed to fetch habits")
        return []


async def _checkin_habit(habit_name: str) -> str | None:
    """習慣名でチェックインを実行. 成功時は習慣名を返す."""
    v1_token = _get_v1_token()
    client = TickTickClient(
        client_id=os.environ["TICKTICK_CLIENT_ID"],
        client_secret=os.environ["TICKTICK_CLIENT_SECRET"],
        username=os.environ.get("TICKTICK_USERNAME", ""),
        password=os.environ.get("TICKTICK_PASSWORD", ""),
        v1_access_token=v1_token,
    )
    try:
        await client.connect()
        habits = await client.get_all_habits()

        # 名前の部分一致で検索
        target = None
        for h in habits:
            if habit_name.lower() in h.name.lower():
                target = h
                break

        if not target:
            logger.warning("Habit not found: %s", habit_name)
            return None

        await client.checkin_habit(target.id)
        logger.info("Checked in habit: %s", target.name)
        return target.name
    finally:
        await client.disconnect()


def checkin_habit(habit_name: str) -> str | None:
    """習慣をチェックイン（同期）. 成功時は正式な習慣名を返す."""
    if not os.environ.get("TICKTICK_USERNAME") or not os.environ.get("TICKTICK_PASSWORD"):
        return None
    try:
        return _run_async(_checkin_habit(habit_name))
    except Exception:
        logger.exception("Failed to checkin habit: %s", habit_name)
        return None
