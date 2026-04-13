"""
iMessage/SMS connector — Phase 3.

Reads from ~/Library/Messages/chat.db (SQLite).
Requires Full Disk Access for Terminal/Python process.

Safety: copies DB to a temp file before opening to avoid SQLite lock errors
while Messages.app is running.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from connectors.base import BaseConnector
import config
from models import RawMessage

logger = logging.getLogger(__name__)

# Apple epoch: seconds since 2001-01-01 00:00:00 UTC
_APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
# macOS 10.13+ uses nanoseconds; older versions use seconds
_APPLE_EPOCH_NS_THRESHOLD = 1_000_000_000  # if value > this, treat as nanoseconds


def _apple_ts_to_utc(ts: int | float) -> datetime:
    if ts > _APPLE_EPOCH_NS_THRESHOLD:
        ts = ts / 1e9
    return _APPLE_EPOCH + timedelta(seconds=ts)


class IMessageConnector(BaseConnector):
    source_name = "imessage"

    def fetch(self, since: datetime, mock: bool = False) -> list[RawMessage]:
        if mock:
            from tests.mock_data import imessage_messages
            return imessage_messages(since)

        db_path = Path(config.IMESSAGE_DB_PATH).expanduser()
        if not db_path.exists():
            logger.warning(
                "iMessage DB not found at %s — check Full Disk Access permissions", db_path
            )
            return []

        # Copy to temp file to avoid locking Messages.app
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            shutil.copy2(db_path, tmp_path)
            return self._query(tmp_path, since)
        except Exception as exc:
            logger.warning("iMessage fetch failed: %s", exc)
            return []
        finally:
            tmp_path.unlink(missing_ok=True)

    def _query(self, db_path: Path, since: datetime) -> list[RawMessage]:
        # Convert since to Apple epoch seconds for the query
        since_apple = (since - _APPLE_EPOCH).total_seconds() * 1e9  # nanoseconds

        messages = []
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            # TODO (Phase 3): verify column names on target macOS version
            # chat.db schema: message table with ROWID, text, date, handle_id, is_from_me
            rows = conn.execute(
                """
                SELECT ROWID, text, date, handle_id, is_from_me
                FROM message
                WHERE date > ?
                  AND text IS NOT NULL
                  AND text != ''
                ORDER BY date ASC
                LIMIT 500
                """,
                (since_apple,),
            ).fetchall()

        for row in rows:
            ts = _apple_ts_to_utc(row["date"])
            messages.append(
                RawMessage(
                    id=f"imessage_{row['ROWID']}",
                    source=self.source_name,
                    timestamp=ts,
                    body_text=row["text"],
                    metadata={"handle_id": row["handle_id"], "is_from_me": bool(row["is_from_me"])},
                )
            )

        logger.debug("imessage: fetched %d messages since %s", len(messages), since.date())
        return messages
