"""Slack Bot のビジネスロジックのテスト.

bot.py は import 時に Slack App を初期化するため、
テスト対象のロジックを直接再現してテストする。
"""


# ---------------------------------------------------------------------------
# _find_task() のロジック再現
# ---------------------------------------------------------------------------

def _find_task(hint: str, all_tasks: list[dict]) -> dict | None:
    """bot._find_task() のロジックを再現."""
    if not hint:
        return all_tasks[0] if len(all_tasks) == 1 else None

    if hint.isdigit():
        idx = int(hint) - 1
        if 0 <= idx < len(all_tasks):
            return all_tasks[idx]

    for task in all_tasks:
        if hint.lower() in task.get("title", "").lower():
            return task

    return None


# ---------------------------------------------------------------------------
# _format_categorized() のロジック再現
# ---------------------------------------------------------------------------

def _format_categorized(categorized: dict[str, list[dict]], order: list[str]) -> str:
    """bot._format_categorized() のロジックを再現."""
    label_map = {
        "overdue": "【期限切れ】",
        "today": "【今日】",
        "week": "【今週】",
        "no_date": "【期限未設定】",
    }
    lines = []
    idx = 1
    for cat_key in order:
        tasks = categorized.get(cat_key, [])
        if not tasks:
            continue
        lines.append(f"\n{label_map[cat_key]}")
        for t in tasks:
            due = t.get("dueDate", "")
            due_suffix = f" (期限: {due[:10]})" if due else ""
            content = t.get("content", "").strip()
            content_suffix = f"\n   → {content}" if content else ""
            lines.append(f"{idx}. {t.get('title', '(no title)')}{due_suffix}{content_suffix}")
            idx += 1
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# _format_habits() のロジック再現
# ---------------------------------------------------------------------------

def _format_habits(habits: list[dict]) -> str:
    """bot._format_habits() のロジックを再現."""
    lines = ["\n\n【習慣】"]
    for h in habits:
        checked = h.get("checked_today", False)
        mark = "✅" if checked else "⬜"
        lines.append(f"{mark} {h.get('name', '(no name)')}")
    return "\n".join(lines)


# ===========================================================================
# Tests
# ===========================================================================

class TestFindTask:
    """_find_task() のタスク検索ロジック."""

    def setup_method(self):
        self.tasks = [
            {"title": "買い物リスト作成", "id": "1", "_project_id": "p1"},
            {"title": "レポート提出", "id": "2", "_project_id": "p1"},
            {"title": "ジョギング", "id": "3", "_project_id": "p2"},
        ]

    def test_find_by_number(self):
        assert _find_task("1", self.tasks)["title"] == "買い物リスト作成"

    def test_find_by_number_last(self):
        assert _find_task("3", self.tasks)["title"] == "ジョギング"

    def test_number_out_of_range(self):
        assert _find_task("0", self.tasks) is None
        assert _find_task("4", self.tasks) is None

    def test_find_by_partial_name(self):
        assert _find_task("レポート", self.tasks)["title"] == "レポート提出"

    def test_find_case_insensitive(self):
        tasks = [{"title": "Test Task", "id": "1", "_project_id": "p1"}]
        assert _find_task("test", tasks)["title"] == "Test Task"

    def test_no_match(self):
        assert _find_task("存在しないタスク", self.tasks) is None

    def test_empty_hint_single_task(self):
        assert _find_task("", [self.tasks[0]])["title"] == "買い物リスト作成"

    def test_empty_hint_multiple_tasks(self):
        assert _find_task("", self.tasks) is None


class TestFormatCategorized:
    """_format_categorized() のフォーマットロジック."""

    def test_basic_formatting(self):
        categorized = {
            "overdue": [{"title": "期限切れタスク", "dueDate": "2026-04-08T00:00:00.000+0000"}],
            "today": [{"title": "今日のタスク", "dueDate": "2026-04-09T00:00:00.000+0000"}],
            "week": [],
        }
        result = _format_categorized(categorized, ["overdue", "today", "week"])
        assert "【期限切れ】" in result
        assert "1. 期限切れタスク" in result
        assert "【今日】" in result
        assert "2. 今日のタスク" in result

    def test_empty_categories_skipped(self):
        categorized = {"overdue": [], "today": [], "week": []}
        result = _format_categorized(categorized, ["overdue", "today", "week"])
        assert result == ""

    def test_sequential_numbering_across_categories(self):
        categorized = {
            "overdue": [{"title": "A", "dueDate": "2026-04-07"}],
            "today": [
                {"title": "B", "dueDate": "2026-04-09"},
                {"title": "C", "dueDate": "2026-04-09"},
            ],
        }
        result = _format_categorized(categorized, ["overdue", "today"])
        assert "1. A" in result
        assert "2. B" in result
        assert "3. C" in result

    def test_no_date_task(self):
        categorized = {"no_date": [{"title": "期限なし"}]}
        result = _format_categorized(categorized, ["no_date"])
        assert "【期限未設定】" in result
        assert "1. 期限なし" in result
        assert "(期限:" not in result


class TestFormatHabits:
    """_format_habits() のフォーマットロジック."""

    def test_checked_habit(self):
        habits = [{"name": "運動", "checked_today": True}]
        result = _format_habits(habits)
        assert "✅ 運動" in result

    def test_unchecked_habit(self):
        habits = [{"name": "読書", "checked_today": False}]
        result = _format_habits(habits)
        assert "⬜ 読書" in result

    def test_missing_checked_defaults_unchecked(self):
        habits = [{"name": "瞑想"}]
        result = _format_habits(habits)
        assert "⬜ 瞑想" in result

    def test_empty(self):
        result = _format_habits([])
        assert "【習慣】" in result

    def test_missing_name(self):
        result = _format_habits([{"id": "1"}])
        assert "(no name)" in result
