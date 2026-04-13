"""
WhatsApp Desktop (Mac) connector — Phase 3.

Reads from:
~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite

Requires Full Disk Access. Copies DB to temp file before reading.
Schema: ZWAMESSAGE table, ZTEXT column, ZMESSAGEDATE in Apple epoch (device-local time).
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

_APPLE_EPOCH_UTC = datetime(2001, 1, 1, tzinfo=timezone.utc)
_EXPECTED_COLUMNS = {"ZTEXT", "ZMESSAGEDATE", "Z_PK"}


def _apple_ts_to_utc(ts: float) -> datetime:
    """Convert Apple epoch (seconds since 2001-01-01) to UTC datetime."""
    return _APPLE_EPOCH_UTC + timedelta(seconds=float(ts))


class WhatsAppConnector(BaseConnector):
    source_name = "whatsapp"

    def fetch(self, since: datetime, mock: bool = False) -> list[RawMessage]:
        if mock:
            from tests.mock_data import whatsapp_messages
            return whatsapp_messages(since)

        db_path = Path(config.WHATSAPP_DB_PATH).expanduser()
        if not db_path.exists():
            logger.warning(
                "WhatsApp DB not found at %s — check Full Disk Access permissions", db_path
            )
            return []

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            shutil.copy2(db_path, tmp_path)
            return self._query(tmp_path, since)
        except Exception as exc:
            logger.warning("WhatsApp fetch failed: %s", exc)
            return []
        finally:
            tmp_path.unlink(missing_ok=True)

    def _validate_schema(self, conn: sqlite3.Connection) -> bool:
        """Check that expected columns exist before querying."""
        cursor = conn.execute("PRAGMA table_info(ZWAMESSAGE)")
        cols = {row[1] for row in cursor.fetchall()}
        missing = _EXPECTED_COLUMNS - cols
        if missing:
            logger.warning(
                "WhatsApp DB schema mismatch — missing columns: %s. "
                "The WhatsApp app may have been updated.",
                missing,
            )
            return False
        return True

    def _query(self, db_path: Path, since: datetime) -> list[RawMessage]:
        since_apple = (since - _APPLE_EPOCH_UTC).total_seconds()
        messages = []

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if not self._validate_schema(conn):
                return []

            rows = conn.execute(
                """
                SELECT Z_PK, ZTEXT, ZMESSAGEDATE
                FROM ZWAMESSAGE
                WHERE ZMESSAGEDATE > ?
                  AND ZTEXT IS NOT NULL
                  AND ZTEXT != ''
                ORDER BY ZMESSAGEDATE ASC
                LIMIT 500
                """,
                (since_apple,),
            ).fetchall()

        for row in rows:
            ts = _apple_ts_to_utc(row["ZMESSAGEDATE"])
            messages.append(
                RawMessage(
                    id=f"whatsapp_{row['Z_PK']}",
                    source=self.source_name,
                    timestamp=ts,
                    body_text=row["ZTEXT"],
                    metadata={},
                )
            )

        logger.debug("whatsapp: fetched %d messages since %s", len(messages), since.date())
        return messages
