"""TickTick OAuth2 初回トークン取得CLI.

使い方:
  python -m src.ticktick.auth
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv

AUTH_URL = "https://ticktick.com/oauth/authorize"
TOKEN_URL = "https://ticktick.com/oauth/token"


def main() -> None:
    load_dotenv()

    client_id = os.environ.get("TICKTICK_CLIENT_ID")
    client_secret = os.environ.get("TICKTICK_CLIENT_SECRET")
    redirect_uri = os.environ.get("TICKTICK_REDIRECT_URI", "http://localhost:8080/callback")
    token_file = Path(os.environ.get("TOKEN_FILE", ".tokens.json"))

    if not client_id or not client_secret:
        print("Error: TICKTICK_CLIENT_ID and TICKTICK_CLIENT_SECRET must be set.")
        sys.exit(1)

    # 1. 認証URLを表示
    params = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "tasks:read tasks:write",
        "state": "nudge-bot",
    })
    print(f"\nOpen this URL in your browser:\n\n  {AUTH_URL}?{params}\n")

    # 2. コードを入力
    code = input("Paste the authorization code here: ").strip()
    if not code:
        print("No code provided.")
        sys.exit(1)

    # 3. トークン交換
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    if resp.status_code != 200:
        print(f"Token exchange failed: {resp.status_code}\n{resp.text}")
        sys.exit(1)

    token_data = resp.json()
    token_file.write_text(json.dumps(token_data, indent=2))
    print(f"\nToken saved to {token_file}")
    print("You can now start the bot.")


if __name__ == "__main__":
    main()
