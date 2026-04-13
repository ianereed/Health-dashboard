"""
Slack connector — Phase 4.

Fetches messages from configured channels since `since` using slack_sdk.WebClient.
Reuses existing SLACK_BOT_TOKEN from .env.
"""
from __future__ import annotations

import logging
from datetime import datetime

from connectors.base import BaseConnector
from models import RawMessage

logger = logging.getLogger(__name__)


class SlackConnector(BaseConnector):
    source_name = "slack"

    def fetch(self, since: datetime, mock: bool = False) -> list[RawMessage]:
        if mock:
            from tests.mock_data import slack_messages
            return slack_messages(since)

        # TODO (Phase 4): implement Slack conversations.history fetch
        # 1. from slack_sdk import WebClient; client = WebClient(token=config.SLACK_BOT_TOKEN)
        # 2. For each channel in config.SLACK_MONITOR_CHANNELS:
        #    result = client.conversations_history(channel=ch, oldest=str(since.timestamp()))
        # 3. Respect Tier 1 rate limits (1 req/min for conversations.history)
        # 4. Return RawMessage list with timestamp normalized to UTC
        logger.warning("slack connector not yet implemented — returning []")
        return []
