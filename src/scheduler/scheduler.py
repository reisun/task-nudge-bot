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
        categorized = ticktick.get_categorized_tasks()
        completed = ticktick.get_todays_completed_tasks()
        total = sum(len(v) for v in categorized.values())
        logger.info("Fetched %d tasks (overdue=%d, today=%d, week=%d, no_date=%d, future=%d), completed=%d",
                     total, len(categorized["overdue"]), len(categorized["today"]),
                     len(categorized["week"]), len(categorized["no_date"]),
                     len(categorized["future"]), len(completed))
        post_tasks(categorized, completed)
    except Exception:
        logger.exception("Daily notification job failed")


def create_scheduler(ticktick: TickTickClient) -> BackgroundScheduler:
    """スケジューラーを作成して返す（まだstart()は呼ばない）."""
    start_hour = int(os.environ.get("NOTIFY_START_HOUR", "9"))
    end_hour = int(os.environ.get("NOTIFY_END_HOUR", "23"))
    minute = int(os.environ.get("NOTIFY_CRON_MINUTE", "0"))
    timezone = os.environ.get("TZ", "Asia/Tokyo")

    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        _notify_job,
        trigger="cron",
        hour=f"{start_hour}-{end_hour}",
        minute=minute,
        args=[ticktick],
        id="hourly_notify",
        name="Hourly task notification",
    )

    logger.info("Scheduler configured: every hour %02d:00-%02d:00 (%s)", start_hour, end_hour, timezone)
    return scheduler
