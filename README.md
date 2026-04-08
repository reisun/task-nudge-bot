# task-nudge-bot

TickTickの今日のタスクをSlackで通知し、双方向チャットで完了を促すbot。

- TickTick Open API (OAuth2) でタスク一覧取得・完了
- Slack Bot (slack_bolt + SocketMode) で定期通知 + スレッド内チャット
- AIナッジ対話: Claude CLIでユーザーの返答に自然に促す応答を生成
- Docker + docker-compose でデプロイ

## セットアップ

### 1. 前提条件

- Docker Desktop (Windows + WSL2)
- TickTick Developer アカウント (https://developer.ticktick.com/)
- Slack App (Socket Mode有効、Bot Token + App-Level Token)
- Claude CLI がホストマシンで認証済み (`claude login` 実行済み)

### 2. Slack App 設定

1. https://api.slack.com/apps でアプリを作成
2. **Socket Mode** を有効化し、App-Level Token (`xapp-...`) を取得
3. **OAuth & Permissions** で以下のBot Token Scopesを追加:
   - `chat:write`
   - `channels:read`
   - `channels:history`
   - `app_mentions:read`
4. **Event Subscriptions** で `message.channels` を購読
5. Bot Token (`xoxb-...`) をコピー
6. Botを対象チャンネルに招待

### 3. TickTick App 設定

1. https://developer.ticktick.com/manage で新規アプリ作成
2. Redirect URI: `http://localhost:8080/callback`
3. Client ID と Client Secret をメモ

### 4. 環境変数の設定

```bash
cp .env.example .env
# .env を編集して実際の値を入力
```

### 5. TickTick OAuth2 トークン取得

初回のみ、手動でトークンを取得します:

```bash
docker compose run --rm bot python -m src.ticktick.auth
```

表示されるURLをブラウザで開き、認可後のコードを入力してください。

### 6. 起動

```bash
docker compose up -d
```

### 7. ログ確認

```bash
docker compose logs -f bot
```

## 動作

- 毎朝9:00 (JST) に今日のタスクをSlackチャンネルに投稿
- スレッドで返信するとAIがナッジ応答
- 「完了 タスク名」と返信するとTickTickでタスクを完了にマーク

## 開発

```bash
# ローカルで直接実行する場合
pip install -r requirements.txt
python -m src.main
```

## プロジェクト構成

```
src/
  main.py           # エントリーポイント
  ticktick/
    client.py       # TickTick APIクライアント
    auth.py         # OAuth2トークン取得CLI
  slack_bot/
    bot.py          # Slack Bot (SocketMode)
  nudge/
    nudge.py        # Claude CLIによるAI応答生成
  scheduler/
    scheduler.py    # APScheduler定期通知
```
