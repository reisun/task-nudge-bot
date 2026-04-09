# task-nudge-bot Design Document

## Overview

TickTickの今日のタスクをSlackで通知し、スレッド内の双方向チャットでタスク完了を促すbot。

## Architecture

```
+------------------+     +------------------+     +------------------+
|   TickTick API   |<--->|  task-nudge-bot   |<--->|   Slack (Socket) |
|   (OAuth2/REST)  |     |   (Python)        |     |   (bolt+Socket)  |
+------------------+     +------------------+     +------------------+
                                |
                                v
                         +------------------+
                         |   Claude CLI     |
                         |   (AI Nudge)     |
                         +------------------+
```

### Components

1. **TickTick Client** (`src/ticktick/`) - OAuth2トークン管理、タスク取得
2. **Slack Bot** (`src/slack_bot/`) - SocketMode接続、メッセージ送受信
3. **AI Nudge** (`src/nudge/`) - Claude CLIでナッジ応答生成
4. **Scheduler** (`src/scheduler/`) - APSchedulerで定期通知
5. **Main** (`src/main.py`) - エントリーポイント

## TickTick Integration

### OAuth2 Flow
- Authorization URL: `https://ticktick.com/oauth/authorize`
- Token URL: `https://ticktick.com/oauth/token`
- Scopes: `tasks:read`, `tasks:write`
- トークンはファイル（`.tokens.json`）に永続化し、起動時に読み込む
- 初回トークン取得は手動（CLIでauth URLを開いてcodeを入力）

### API Endpoints
- `GET https://api.ticktick.com/open/v1/project` - プロジェクト一覧
- `GET https://api.ticktick.com/open/v1/project/{id}/data` - プロジェクト内タスク取得
- `POST https://api.ticktick.com/open/v1/task/{taskId}/complete` - タスク完了

### Rate Limits
- 100 requests/min, 300 requests/5min

## Slack Bot

### Connection
- SocketMode（公開URL不要）
- `SLACK_BOT_TOKEN` (xoxb-*) + `SLACK_APP_TOKEN` (xapp-*)

### Required Scopes
- `chat:write` - メッセージ送信
- `channels:read` - チャンネル情報
- `channels:history` - メッセージ履歴
- `app_mentions:read` - メンション受信

### Event Subscriptions
- `message` - スレッド内返信検知

### Message Flow
1. 毎朝指定時刻に、今日のタスク一覧をSlackチャンネルに投稿
2. ユーザーがスレッドで返信
3. Botがスレッド内でAIナッジ応答を返す
4. ユーザーが「完了」等と返信 → TickTickでタスクを完了にする

## AI Nudge

### Implementation
- `claude` CLIをsubprocessで呼び出し
- システムプロンプトでナッジ役を指定
- ユーザーの返答 + タスク情報をコンテキストとして渡す
- 応答は日本語、カジュアルな口調

### Prompt Strategy
```
あなたはタスク管理のナッジbotです。
ユーザーが今日やるべきタスクについて話しています。
優しく、でも具体的に「じゃあこれからやろうか」と促してください。
タスクの完了を報告されたら褒めてください。
```

## Scheduler

- APScheduler (BackgroundScheduler)
- Cron式で毎朝の通知時刻を設定（デフォルト: 09:00 JST）
- 設定は環境変数 `NOTIFY_CRON_HOUR`, `NOTIFY_CRON_MINUTE` で変更可能

## Configuration (.env)

```
# TickTick OAuth2
TICKTICK_CLIENT_ID=
TICKTICK_CLIENT_SECRET=
TICKTICK_REDIRECT_URI=http://localhost:8080/callback

# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_CHANNEL_ID=C...

# Scheduler
NOTIFY_CRON_HOUR=9
NOTIFY_CRON_MINUTE=0
TZ=Asia/Tokyo
```

## Docker

### Dockerfile
- Python 3.11-slim base
- Claude CLI pre-installed
- pip install from requirements.txt

### docker-compose.yml
- Single service: `bot`
- Volume mount for `.env` and token storage
- Restart policy: `unless-stopped`

## Phase 2 (Out of Scope)
- 習慣(Habits)対応
- 音声対応
- 複数ユーザー対応
- Web UI for OAuth flow
