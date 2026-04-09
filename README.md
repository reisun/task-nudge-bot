# task-nudge-bot

TickTick のタスクを Slack で定期通知し、チャンネル内の会話でタスク支援・生活支援を行う bot。

- TickTick Open API (OAuth2) でタスク取得・完了
- Slack Bot (slack_bolt + SocketMode) で定期通知 + チャンネル内チャット
- AI 応答: Claude CLI でユーザーの発言に自然に応じる（WebSearch/WebFetch 対応）
- タスクをカテゴリ別（期限切れ / 今日 / 今週）に分類して通知
- Docker + docker-compose でデプロイ

## セットアップ

### 1. 前提条件

- Docker Desktop (Windows + WSL2)
- TickTick Developer アカウント (https://developer.ticktick.com/)
- Slack App (Socket Mode 有効、Bot Token + App-Level Token)
- Claude CLI がホストマシンで認証済み (`claude login` 実行済み、ANTHROPIC_API_KEY は不要)

### 2. Slack App 設定

1. https://api.slack.com/apps でアプリを作成
2. **Socket Mode** を有効化し、App-Level Token (`xapp-...`) を取得
3. **OAuth & Permissions** で以下の Bot Token Scopes を追加:
   - `chat:write`
   - `channels:read`
   - `channels:history`
   - `reactions:write`
4. **Event Subscriptions** で `message.channels` を購読
5. Bot Token (`xoxb-...`) をコピー
6. Bot を対象チャンネルに招待

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

表示される URL をブラウザで開き、認可後のコードを入力してください。

### 6. 起動

```bash
docker compose up -d
```

### 7. ログ確認

```bash
docker compose logs -f bot
```

## 動作

- **定期通知**: 毎時 (`NOTIFY_START_HOUR`〜`NOTIFY_END_HOUR`、デフォルト 7:00〜23:00) にタスクを通知
  - 期限切れ / 今日 / 今週 のカテゴリ別に表示（期限未設定は除外）
  - Claude がタスクと時間帯に応じたメッセージを生成
  - `@channel` メンションで通知
- **チャンネル会話**: チャンネルに直接メッセージを送ると AI が応答（タスク支援・生活支援）
- **スレッド返信**: 定時通知のスレッド内でも AI が応答
- **タスク完了**: 「完了 タスク名」と返信すると TickTick でタスクを完了にマーク
- **進捗表示**: 応答生成中は「考え中...」メッセージを表示し、完了時に置き換え

## 環境変数

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | App-Level Token for Socket Mode (`xapp-...`) |
| `SLACK_CHANNEL_ID` | 通知先チャンネル ID |
| `TICKTICK_CLIENT_ID` | TickTick OAuth2 Client ID |
| `TICKTICK_CLIENT_SECRET` | TickTick OAuth2 Client Secret |
| `TICKTICK_REDIRECT_URI` | TickTick OAuth2 Redirect URI |
| `NOTIFY_START_HOUR` | 通知開始時刻 (デフォルト: 7) |
| `NOTIFY_END_HOUR` | 通知終了時刻 (デフォルト: 23) |
| `NOTIFY_CRON_MINUTE` | 通知分 (デフォルト: 0) |
| `TZ` | タイムゾーン (デフォルト: Asia/Tokyo) |

> Claude の認証はホストの `~/.claude` をシンボリックリンクで共有しています。トークンのリフレッシュはホスト側で行われ、コンテナに即時反映されます。

## プロジェクト構成

```
src/
  main.py           # エントリーポイント
  ticktick/
    client.py       # TickTick APIクライアント（カテゴリ別タスク取得）
    auth.py         # OAuth2トークン取得CLI
  slack_bot/
    bot.py          # Slack Bot (SocketMode) — 通知・会話・完了処理
  nudge/
    nudge.py        # Claude CLIによるAI応答・通知メッセージ生成
  scheduler/
    scheduler.py    # APScheduler毎時通知
```
