"""TickTick API client — OAuth2トークン管理 + タスク取得・完了."""

import json
import os
from datetime import date, datetime
from pathlib import Path

import httpx

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

    def _headers(self) -> dict[str, str]:
        if not self._access_token:
            raise RuntimeError("No access token. Run auth.py first.")
        return {"Authorization": f"Bearer {self._access_token}"}

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    def _get(self, path: str) -> dict | list:
        """GET request with auto-retry on 401 (token refresh)."""
        resp = httpx.get(f"{BASE_URL}{path}", headers=self._headers())
        if resp.status_code == 401:
            self.refresh_token()
            resp = httpx.get(f"{BASE_URL}{path}", headers=self._headers())
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

    def get_todays_tasks(self) -> list[dict]:
        """今日が期限のタスクを全プロジェクトから取得."""
        today = date.today().isoformat()  # "YYYY-MM-DD"
        all_tasks = self.get_all_tasks()
        return [t for t in all_tasks if (t.get("dueDate") or "")[:10] == today]

    def complete_task(self, project_id: str, task_id: str) -> None:
        """タスクを完了にする."""
        resp = httpx.post(
            f"{BASE_URL}/task/{task_id}/complete",
            headers=self._headers(),
        )
        if resp.status_code == 401:
            self.refresh_token()
            resp = httpx.post(
                f"{BASE_URL}/task/{task_id}/complete",
                headers=self._headers(),
            )
        resp.raise_for_status()
