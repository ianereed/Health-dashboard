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
import time

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

_RATE_LIMIT_SECONDS = 10
_user_last_query: dict[str, float] = {}
_in_flight: set[str] = set()

_GREETINGS = frozenset({"help", "?", "hi", "hello", "hey", "thanks", "thank you", "thx", "ty"})
_HELP_TEXT = (
    "Hi — I answer questions about your finances using local data.\n\n"
    "Examples:\n"
    "  • _how much did I spend on groceries last month?_\n"
    "  • _what's my savings rate?_\n"
    "  • _what did I spend at Costco this year?_\n"
    "  • _summarize my financial plan_\n\n"
    "Receipts photographed in #ian-image-intake also land here automatically.\n"
    "Heads up: I take 30s–2min per answer (local model on the mini)."
)


def run() -> None:
    db.init_db()

    if not config.SLACK_APP_TOKEN:
        raise RuntimeError("SLACK_APP_TOKEN not set — add it to .env")
    if not config.SLACK_BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN not set — add it to .env")

    if not config.ALLOWED_SLACK_USER_IDS:
        logger.warning(
            "finance-bot: ALLOWED_SLACK_USER_IDS is not set — "
            "any workspace member can DM the bot and query your financial data"
        )

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

        sender = event.get("user", "")
        if config.ALLOWED_SLACK_USER_IDS and sender not in config.ALLOWED_SLACK_USER_IDS:
            logger.warning("finance-bot: rejected DM from unauthorized user %s", sender)
            say("Sorry, you're not authorized to use this bot.")
            return

        if question.lower() in _GREETINGS:
            say(_HELP_TEXT)
            return

        if sender in _in_flight:
            say("_Still working on your last question — give me a sec._")
            return

        now = time.monotonic()
        elapsed = now - _user_last_query.get(sender, 0)
        if elapsed < _RATE_LIMIT_SECONDS:
            remaining = max(1, int(_RATE_LIMIT_SECONDS - elapsed))
            say(f"_Asked too quickly — wait {remaining}s._")
            return

        logger.info("finance-bot: received DM from %s (len=%d)", sender, len(question))

        thinking_resp = say("_Thinking..._")
        channel_id = event["channel"]
        thinking_ts = thinking_resp["ts"]

        def _on_stage(label: str) -> None:
            try:
                app.client.chat_update(
                    channel=channel_id,
                    ts=thinking_ts,
                    text=f"_{label}..._",
                )
            except Exception as exc:  # don't let a transient Slack error kill the answer
                logger.warning("finance-bot: chat_update (stage) failed: %s", exc)

        _in_flight.add(sender)
        try:
            answer = query_engine.answer(question, on_stage=_on_stage)
        finally:
            _in_flight.discard(sender)
            _user_last_query[sender] = time.monotonic()

        app.client.chat_update(
            channel=channel_id,
            ts=thinking_ts,
            text=answer,
        )
        logger.info("finance-bot: answered DM for %s", sender)

    logger.info("finance-bot: starting Socket Mode handler")
    handler = SocketModeHandler(app, app_token)
    handler.start()
