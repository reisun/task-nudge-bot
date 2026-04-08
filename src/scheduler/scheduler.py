"""Scheduler — APSchedulerで毎朝タスク通知."""

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from src.slack_bot.bot import post_tasks
from src.ticktick.client import TickTickClient

logger = logging.getLogger(__name__)


def _notify_job(ticktick: TickTickClient) -> None:
    """タスクを取得してSlackに投稿するジョブ."""
    try:
        tasks = ticktick.get_todays_tasks()
        logger.info("Fetched %d tasks for today", len(tasks))
        post_tasks(tasks)
    except Exception:
        logger.exception("Daily notification job failed")


def create_scheduler(ticktick: TickTickClient) -> BackgroundScheduler:
    """スケジューラーを作成して返す（まだstart()は呼ばない）."""
    hour = int(os.environ.get("NOTIFY_CRON_HOUR", "9"))
    minute = int(os.environ.get("NOTIFY_CRON_MINUTE", "0"))
    timezone = os.environ.get("TZ", "Asia/Tokyo")

    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        _notify_job,
        trigger="cron",
        hour=hour,
        minute=minute,
        args=[ticktick],
        id="daily_notify",
        name="Daily task notification",
    )

    logger.info("Scheduler configured: %02d:%02d (%s)", hour, minute, timezone)
    return scheduler
