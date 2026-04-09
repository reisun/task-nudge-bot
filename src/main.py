"""task-nudge-bot エントリーポイント."""

import logging
import sys

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()

    # 環境変数チェック
    import os

    required = [
        "TICKTICK_CLIENT_ID",
        "TICKTICK_CLIENT_SECRET",
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
        "SLACK_CHANNEL_ID",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    # コンポーネント初期化
    from src.ticktick.client import TickTickClient
    from src.slack_bot import bot
    from src.scheduler.scheduler import create_scheduler

    logger.info("Initializing TickTick client...")
    ticktick = TickTickClient()

    # Slack botにTickTickクライアントを渡す
    bot.ticktick_client = ticktick

    logger.info("Starting scheduler...")
    scheduler = create_scheduler(ticktick)
    scheduler.start()

    logger.info("Starting Slack SocketMode handler...")
    handler = bot.start_socket_mode()

    try:
        handler.start()  # ブロッキング
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        scheduler.shutdown()
        logger.info("Bye!")


if __name__ == "__main__":
    main()
