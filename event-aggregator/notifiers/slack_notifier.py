"""
Slack notifier — sends digest messages to the user via DM.

Reuses SLACK_BOT_TOKEN. Target: SLACK_DIGEST_USER_ID (your Slack user ID).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def send_dm(blocks: list[dict[str, Any]], fallback_text: str) -> bool:
    """
    Send a Slack DM to the configured user. Returns True on success.
    blocks: Slack Block Kit payload
    fallback_text: plain-text summary for notifications
    """
    try:
        import config
        if not config.SLACK_BOT_TOKEN or not config.SLACK_DIGEST_USER_ID:
            logger.warning("Slack notifier: SLACK_BOT_TOKEN or SLACK_DIGEST_USER_ID not set")
            return False

        from slack_sdk import WebClient
        client = WebClient(token=config.SLACK_BOT_TOKEN)
        result = client.chat_postMessage(
            channel=config.SLACK_DIGEST_USER_ID,
            text=fallback_text,
            blocks=blocks,
        )
        return bool(result.get("ok"))
    except Exception as exc:
        logger.warning("Slack notifier: failed to send DM: %s", exc)
        return False
