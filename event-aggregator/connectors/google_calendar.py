"""
Google Calendar connector — Phase 6.

Reads pending invites (responseStatus == "needsAction") since `since`.
Also used by the calendar analyzer for the full year-ahead scan.
"""
from __future__ import annotations

import logging
from datetime import datetime

from connectors.base import BaseConnector
from models import RawMessage

logger = logging.getLogger(__name__)


class GoogleCalendarConnector(BaseConnector):
    source_name = "gcal"

    def fetch(self, since: datetime, mock: bool = False) -> list[RawMessage]:
        if mock:
            from tests.mock_data import gcal_messages
            return gcal_messages(since)

        # TODO (Phase 6): implement GCal pending invite reader
        # 1. Load credentials from config.GCAL_TOKEN_JSON
        # 2. service.events().list(calendarId="primary", updatedMin=since.isoformat(),
        #                          singleEvents=True, orderBy="updated")
        # 3. Filter to responseStatus == "needsAction"
        # 4. body_text = f"{event['summary']} on {event['start']} at {event.get('location','')}"
        logger.warning("gcal connector not yet implemented — returning []")
        return []
