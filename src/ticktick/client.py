"""TickTick API client — OAuth2トークン管理 + タスク取得・完了."""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

JST = ZoneInfo("Asia/Tokyo")


def _parse_due_date_jst(due_str: str) -> date:
    """TickTickのdueDate文字列をJSTの日付に変換.

    TickTickは "2026-04-10T15:00:00.000+0000" のようなUTC形式を返す。
    これをJSTに変換して日付部分を返す。
    """
    try:
        # ISO形式パース（+0000 → +00:00 に正規化）
        normalized = due_str.replace("+0000", "+00:00").replace("-0000", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt.astimezone(JST).date()
    except (ValueError, TypeError):
        # フォールバック: 先頭10文字を日付として扱う
        return date.fromisoformat(due_str[:10])


AUTH_URL = "https://ticktick.com/oauth/authorize"
BASE_URL = "https://api.ticktick.com/open/v1"
TOKEN_URL = "https://ticktick.com/oauth/token"
TOKEN_FILE = Path(os.environ.get("TOKEN_FILE", ".tokens.json"))


class TickTickClient:
    """TickTick Open API クライアント."""

    def __init__(self) -> None:
        self.client_id = os.environ["TICKTICK_CLIENT_ID"]
        self.client_secret = os.environ["TICKTICK_CLIENT_SECRET"]
        self.redirect_uri = os.environ.get(
            "TICKTICK_REDIRECT_URI", "http://localhost:8080/callback"
        )
        self._access_token: str | None = None
        self._load_token()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _load_token(self) -> None:
        """ファイルからトークンを読み込む."""
        if TOKEN_FILE.exists():
            data = json.loads(TOKEN_FILE.read_text())
            self._access_token = data.get("access_token")

    def _save_token(self, data: dict) -> None:
        """トークンをファイルに保存."""
        TOKEN_FILE.write_text(json.dumps(data, indent=2))
        self._access_token = data.get("access_token")

    def refresh_token(self) -> None:
        """リフレッシュトークンでアクセストークンを更新."""
        if not TOKEN_FILE.exists():
            raise RuntimeError("No token file found. Run auth.py first.")

        data = json.loads(TOKEN_FILE.read_text())
        refresh = data.get("refresh_token")
        if not refresh:
            raise RuntimeError("No refresh_token in token file.")

        resp = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        self._save_token(resp.json())

    def get_auth_url(self) -> str:
        """OAuth認証URLを生成."""
        from urllib.parse import urlencode
        params = urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "tasks:read tasks:write",
            "state": "nudge-bot",
        })
        return f"{AUTH_URL}?{params}"

    def exchange_code(self, code: str) -> None:
        """認証コードをトークンに交換して保存."""
        resp = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        self._save_token(resp.json())

    def _headers(self) -> dict[str, str]:
        if not self._access_token:
            raise RuntimeError("No access token. Run auth.py first.")
        return {"Authorization": f"Bearer {self._access_token}"}

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    def _get(self, path: str) -> dict | list:
        """GET request with auto-retry on 401 (token refresh) and timeout retry."""
        timeout = httpx.Timeout(30.0, connect=10.0)
        try:
            resp = httpx.get(f"{BASE_URL}{path}", headers=self._headers(), timeout=timeout)
        except httpx.ConnectTimeout:
            # リトライ1回
            resp = httpx.get(f"{BASE_URL}{path}", headers=self._headers(), timeout=timeout)
        if resp.status_code == 401:
            self.refresh_token()
            resp = httpx.get(f"{BASE_URL}{path}", headers=self._headers(), timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def get_projects(self) -> list[dict]:
        """プロジェクト一覧を取得."""
        return self._get("/project")

    def get_project_data(self, project_id: str) -> dict:
        """プロジェクト内のタスクデータを取得."""
        return self._get(f"/project/{project_id}/data")

    def get_all_tasks(self) -> list[dict]:
        """未完了タスクを全プロジェクトから取得."""
        projects = self.get_projects()
        tasks: list[dict] = []

        for proj in projects:
            try:
                data = self.get_project_data(proj["id"])
            except httpx.HTTPStatusError:
                continue
            for task in data.get("tasks", []):
                if task.get("status", 0) != 0:
                    continue  # 完了済みはスキップ
                task["_project_id"] = proj["id"]
                task["_project_name"] = proj.get("name", "")
                tasks.append(task)

        return tasks

    def get_categorized_tasks(self) -> dict[str, list[dict]]:
        """未完了タスクを日付カテゴリ別に分類して返す.

        カテゴリ:
          overdue  — 期限切れ
          today    — 今日が期限
          week     — 今週中（明日〜週末）
          no_date  — 期限未設定
          future   — 来週以降
        """
        today_jst = datetime.now(JST).date()
        week_end_jst = today_jst + timedelta(days=(6 - today_jst.weekday()))  # 今週の日曜

        categories: dict[str, list[dict]] = {
            "overdue": [],
            "today": [],
            "week": [],
            "no_date": [],
            "future": [],
        }

        for task in self.get_all_tasks():
            due_utc = task.get("dueDate", "")
            if not due_utc:
                categories["no_date"].append(task)
                continue
            due_jst = _parse_due_date_jst(due_utc)
            if due_jst < today_jst:
                categories["overdue"].append(task)
            elif due_jst == today_jst:
                categories["today"].append(task)
            elif due_jst <= week_end_jst:
                categories["week"].append(task)
            else:
                categories["future"].append(task)

        return categories

    def get_todays_completed_tasks(self) -> list[dict]:
        """今日完了したタスクを取得."""
        today_start_jst = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start_jst = today_start_jst + timedelta(days=1)
        # TickTick APIはUTC形式を期待
        from_utc = today_start_jst.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S+0000")
        to_utc = tomorrow_start_jst.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S+0000")

        timeout = httpx.Timeout(30.0, connect=10.0)
        resp = httpx.post(
            f"{BASE_URL}/task/completed",
            headers=self._headers(),
            json={"from": from_utc, "to": to_utc},
            timeout=timeout,
        )
        if resp.status_code == 401:
            self.refresh_token()
            resp = httpx.post(
                f"{BASE_URL}/task/completed",
                headers=self._headers(),
                json={"from": from_utc, "to": to_utc},
                timeout=timeout,
            )
        resp.raise_for_status()
        tasks = resp.json() if isinstance(resp.json(), list) else []

        # APIのfrom/toが効かない場合があるため、クライアント側でJSTでフィルタ
        today_date_jst = today_start_jst.date()
        result = []
        for t in tasks:
            completed_utc = t.get("completedTime", "")
            if not completed_utc:
                continue
            completed_jst = _parse_due_date_jst(completed_utc)
            if completed_jst == today_date_jst:
                result.append(t)
        return result

    def complete_task(self, project_id: str, task_id: str) -> None:
        """タスクを完了にする."""
        timeout = httpx.Timeout(30.0, connect=10.0)
        resp = httpx.post(
            f"{BASE_URL}/project/{project_id}/task/{task_id}/complete",
            headers=self._headers(),
            timeout=timeout,
        )
        if resp.status_code == 401:
            self.refresh_token()
            resp = httpx.post(
                f"{BASE_URL}/project/{project_id}/task/{task_id}/complete",
                headers=self._headers(),
                timeout=timeout,
            )
        resp.raise_for_status()
