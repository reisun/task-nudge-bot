"""TickTick Habits — V2 API経由で習慣情報を取得."""

import asyncio
import json
import logging
import os
from pathlib import Path

from ticktick_sdk import TickTickClient

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


async def _fetch_habits() -> list[dict]:
    """V2 APIから習慣一覧を取得."""
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
        result = []
        for h in habits:
            result.append({
                "id": h.id,
                "name": h.name,
                "status": getattr(h, "status", None),
                "goal": getattr(h, "goal", None),
                "frequency": getattr(h, "frequency", None),
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
