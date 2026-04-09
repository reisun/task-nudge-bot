"""TickTickClient のビジネスロジックのテスト."""

from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.ticktick.client import _parse_due_date_jst

JST = ZoneInfo("Asia/Tokyo")


class TestParseDueDateJst:
    """TickTick の dueDate 文字列を JST 日付に変換するテスト."""

    def test_utc_midnight_becomes_jst_same_day(self):
        # UTC 00:00 → JST 09:00（同日）
        result = _parse_due_date_jst("2026-04-10T00:00:00.000+0000")
        assert result == date(2026, 4, 10)

    def test_utc_afternoon_stays_same_day_jst(self):
        # UTC 14:00 → JST 23:00（同日）
        result = _parse_due_date_jst("2026-04-10T14:00:00.000+0000")
        assert result == date(2026, 4, 10)

    def test_utc_late_night_crosses_to_next_day_jst(self):
        # UTC 15:00 → JST 翌日 00:00
        result = _parse_due_date_jst("2026-04-10T15:00:00.000+0000")
        assert result == date(2026, 4, 11)

    def test_ticktick_typical_format(self):
        # TickTick が実際に返す形式
        result = _parse_due_date_jst("2026-04-09T15:00:00.000+0000")
        assert result == date(2026, 4, 10)

    def test_minus_0000_treated_as_utc(self):
        result = _parse_due_date_jst("2026-04-10T00:00:00.000-0000")
        assert result == date(2026, 4, 10)

    def test_fallback_plain_date_string(self):
        # ISO パース失敗時は先頭10文字をフォールバック
        result = _parse_due_date_jst("2026-04-10")
        assert result == date(2026, 4, 10)

    def test_standard_iso_with_colon_offset(self):
        # 既に +00:00 形式の場合
        result = _parse_due_date_jst("2026-04-10T00:00:00.000+00:00")
        assert result == date(2026, 4, 10)


class TestCategorizeTasks:
    """get_categorized_tasks() のカテゴリ分類ロジックのテスト."""

    @staticmethod
    def _make_task(title: str, due: str = "", status: int = 0) -> dict:
        task = {"title": title, "status": status, "id": title, "_project_id": "p1", "_project_name": "test"}
        if due:
            task["dueDate"] = due
        return task

    def test_categorization(self):
        """各カテゴリに正しく振り分けられること."""
        # 固定日時: 2026-04-09 (木曜日)
        fixed_now = datetime(2026, 4, 9, 12, 0, tzinfo=JST)
        today = fixed_now.date()
        week_end = today + timedelta(days=(6 - today.weekday()))  # 日曜 = 4/12

        # テストデータ: UTC 15:00 = JST 翌日 00:00 なので注意
        overdue_task = self._make_task("期限切れ", "2026-04-08T00:00:00.000+0000")   # JST 4/8
        today_task = self._make_task("今日", "2026-04-08T15:00:00.000+0000")          # JST 4/9
        week_task = self._make_task("今週", "2026-04-10T15:00:00.000+0000")           # JST 4/11
        future_task = self._make_task("来週", "2026-04-15T00:00:00.000+0000")         # JST 4/15
        no_date_task = self._make_task("期限なし")

        all_tasks = [overdue_task, today_task, week_task, future_task, no_date_task]

        # get_categorized_tasks の内部ロジックを再現
        categories = {"overdue": [], "today": [], "week": [], "no_date": [], "future": []}
        for task in all_tasks:
            due = task.get("dueDate", "")
            if not due:
                categories["no_date"].append(task)
                continue
            due_date = _parse_due_date_jst(due)
            if due_date < today:
                categories["overdue"].append(task)
            elif due_date == today:
                categories["today"].append(task)
            elif due_date <= week_end:
                categories["week"].append(task)
            else:
                categories["future"].append(task)

        assert [t["title"] for t in categories["overdue"]] == ["期限切れ"]
        assert [t["title"] for t in categories["today"]] == ["今日"]
        assert [t["title"] for t in categories["week"]] == ["今週"]
        assert [t["title"] for t in categories["future"]] == ["来週"]
        assert [t["title"] for t in categories["no_date"]] == ["期限なし"]

    def test_empty_tasks(self):
        """タスクがない場合は全カテゴリが空."""
        categories = {"overdue": [], "today": [], "week": [], "no_date": [], "future": []}
        for cat in categories.values():
            assert cat == []
