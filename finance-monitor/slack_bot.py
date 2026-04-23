"""
Slack Finance Bot — listens for DMs and answers finance questions locally.

Uses Socket Mode (outbound WebSocket — no inbound port binding required).
Only responds to direct messages; ignores all channel messages for privacy.

Credentials stored in .env:
  SLACK_APP_TOKEN=xapp-...   (Socket Mode App-Level Token)
  SLACK_BOT_TOKEN=xoxb-...   (Bot User OAuth Token)
"""
import logging
import sys

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import config
import db
import query_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def run() -> None:
    db.init_db()

    if not config.SLACK_APP_TOKEN:
        raise RuntimeError("SLACK_APP_TOKEN not set — add it to .env")
    if not config.SLACK_BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN not set — add it to .env")

    bot_token = config.SLACK_BOT_TOKEN
    app_token = config.SLACK_APP_TOKEN

    app = App(token=bot_token)

    @app.event("message")
    def handle_message(event, say, logger):
        # DMs only — channel messages are visible to others in the workspace
        if event.get("channel_type") != "im":
            return
        # Skip bot messages (echoes of our own replies)
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        question = (event.get("text") or "").strip()
        if not question:
            return

        logger.info("finance-bot: received DM (len=%d)", len(question))

        # Acknowledge immediately so the user knows we're working
        thinking_resp = say("_Thinking..._")

        answer = query_engine.answer(question)

        # Replace the "Thinking..." message with the real answer
        app.client.chat_update(
            channel=event["channel"],
            ts=thinking_resp["ts"],
            text=answer,
        )
        logger.info("finance-bot: answered DM")

    logger.info("finance-bot: starting Socket Mode handler")
    handler = SocketModeHandler(app, app_token)
    handler.start()
