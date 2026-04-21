"""Scheduler — APSchedulerで毎朝タスク通知."""

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from src.slack_bot.bot import post_tasks
from src.ticktick.client import TickTickClient
from src.ticktick.habits import get_habits

logger = logging.getLogger(__name__)


def _notify_job(ticktick: TickTickClient) -> None:
    """タスクを取得してSlackに投稿するジョブ."""
    try:
        categorized = ticktick.get_categorized_tasks()
        completed = ticktick.get_todays_completed_tasks()
        habits = get_habits()
        total = sum(len(v) for v in categorized.values())
        logger.info("Fetched %d tasks (overdue=%d, today=%d, week=%d, no_date=%d, future=%d), completed=%d, habits=%d",
                     total, len(categorized["overdue"]), len(categorized["today"]),
                     len(categorized["week"]), len(categorized["no_date"]),
                     len(categorized["future"]), len(completed), len(habits))
        post_tasks(categorized, completed, habits)
    except Exception:
        logger.exception("Daily notification job failed")


def create_scheduler(ticktick: TickTickClient) -> BackgroundScheduler:
    """スケジューラーを作成して返す（まだstart()は呼ばない）."""
    notify_hours = os.environ.get("NOTIFY_HOURS", "")
    if notify_hours:
        hour_spec = notify_hours
    else:
        start_hour = int(os.environ.get("NOTIFY_START_HOUR", "9"))
        end_hour = int(os.environ.get("NOTIFY_END_HOUR", "23"))
        hour_spec = f"{start_hour}-{end_hour}"
    minute = int(os.environ.get("NOTIFY_CRON_MINUTE", "0"))
    timezone = os.environ.get("TZ", "Asia/Tokyo")

    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        _notify_job,
        trigger="cron",
        hour=hour_spec,
        minute=minute,
        args=[ticktick],
        id="task_notify",
        name="Task notification",
    )

    logger.info("Scheduler configured: hour=%s minute=%d (%s)", hour_spec, minute, timezone)
    return scheduler
