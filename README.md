# task-nudge-bot

**task-nudge-bot**: TickTickの今日のタスクをSlackで通知し、双方向チャットで完了を促すbot
- TickTick Open API (OAuth2) でトークン管理、今日のタスク一覧取得
- Slack Bot (slack_bolt + SocketMode) で定期通知 + スレッド内チャット
- AIナッジ対話: claude CLIを使い、ユーザーの返答に対して自然に「じゃあこれからやろうか」と促す応答生成
- Docker + docker-compose でデプロイ可能な構成
- 習慣(Habits)対応・音声対応は Phase 2 として TASK.md に記録
- プロジェクト名: `task-nudge-bot`（既存ディレクトリ `ticktick-token-slack-task-nudge-bot` をリネームまたは新規作成）
