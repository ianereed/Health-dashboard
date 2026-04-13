"""
Gmail connector — Phase 2.

Fetches emails since `since` via Gmail API (OAuth2).
Returns RawMessage with body_text = plain-text email body.
"""
from __future__ import annotations

import logging
from datetime import datetime

from connectors.base import BaseConnector
from models import RawMessage

logger = logging.getLogger(__name__)


class GmailConnector(BaseConnector):
    source_name = "gmail"

    def fetch(self, since: datetime, mock: bool = False) -> list[RawMessage]:
        if mock:
            from tests.mock_data import gmail_messages
            return gmail_messages(since)

        # TODO (Phase 2): implement Gmail API OAuth2 fetch
        # 1. Load credentials from config.GMAIL_CREDENTIALS_JSON / GMAIL_TOKEN_JSON
        # 2. Build service = build("gmail", "v1", credentials=creds)
        # 3. Query: service.users().messages().list(userId="me", q=f"after:{int(since.timestamp())}")
        # 4. For each message: get full payload, extract plain-text part
        # 5. Return RawMessage list (timestamps normalized to UTC)
        logger.warning("gmail connector not yet implemented — returning []")
        return []
