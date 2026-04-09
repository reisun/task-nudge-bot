"""_is_today_habit() のRRULEパースロジックのテスト.

habits.py は import 時に ticktick_sdk を必要とするため、
テスト対象のロジックを直接再現してテストする。
"""

import re
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# Python weekday (0=Mon) → RRULE BYDAY
_WEEKDAY_MAP = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _is_today_habit(repeat_rule: str | None, now: datetime | None = None) -> bool:
    """habits._is_today_habit() のロジックを再現（テスト用に now を注入可能）."""
    if not repeat_rule:
        return True
    today_byday = _WEEKDAY_MAP[(now or datetime.now(JST)).weekday()]
    byday_match = re.search(r"BYDAY=([A-Z,]+)", repeat_rule)
    if not byday_match:
        return True
    return today_byday in byday_match.group(1).split(",")


def _make_now(weekday: int) -> datetime:
    """指定曜日の固定日時を作成. weekday: 0=月, 6=日."""
    # 2026-04-06 は月曜日
    return datetime(2026, 4, 6 + weekday, 12, 0, tzinfo=JST)


class TestIsTodayHabit:
    """RRULE の BYDAY 判定テスト."""

    def test_no_rule_means_every_day(self):
        assert _is_today_habit(None) is True
        assert _is_today_habit("") is True

    def test_no_byday_means_every_day(self):
        assert _is_today_habit("RRULE:FREQ=WEEKLY") is True

    def test_monday_habit_on_monday(self):
        assert _is_today_habit("RRULE:FREQ=WEEKLY;BYDAY=MO", _make_now(0)) is True

    def test_monday_habit_on_tuesday(self):
        assert _is_today_habit("RRULE:FREQ=WEEKLY;BYDAY=MO", _make_now(1)) is False

    def test_multiple_days_match(self):
        assert _is_today_habit("RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR", _make_now(2)) is True

    def test_multiple_days_no_match(self):
        assert _is_today_habit("RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR", _make_now(3)) is False

    def test_weekend_habit_on_saturday(self):
        assert _is_today_habit("RRULE:FREQ=WEEKLY;BYDAY=SA,SU", _make_now(5)) is True

    def test_weekend_habit_on_friday(self):
        assert _is_today_habit("RRULE:FREQ=WEEKLY;BYDAY=SA,SU", _make_now(4)) is False

    def test_all_days(self):
        assert _is_today_habit("RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR,SA,SU", _make_now(6)) is True
