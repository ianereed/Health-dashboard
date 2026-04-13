"""
Google Calendar writer — Phase 2.

Writes CandidateEvents to Google Calendar.
- Pre-write dedup: checks existing events ±1 day by title similarity
- Source attribution: writes "[via event-aggregator | source: {source_type}]" to description
- Idempotent: checks fingerprints before writing
- OAuth2 token stored via keyring (macOS Keychain) with JSON file as fallback
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from models import CandidateEvent, WrittenEvent
import dedup

logger = logging.getLogger(__name__)


def write_event(candidate: CandidateEvent, dry_run: bool = False) -> WrittenEvent | None:
    """
    Write a CandidateEvent to Google Calendar.
    Returns WrittenEvent on success, None on failure or if dry_run.
    """
    fp = dedup.fingerprint(candidate)
    description = f"[via event-aggregator | source: {candidate.source}]"

    if dry_run:
        logger.info(
            "DRY RUN — would create: %r on %s (confidence=%.2f, source=%s)",
            candidate.title,
            candidate.start_dt.date(),
            candidate.confidence,
            candidate.source,
        )
        return None

    # TODO (Phase 2): implement GCal OAuth2 write
    # 1. Load/refresh token via keyring first, fallback to config.GCAL_TOKEN_JSON
    # 2. Build service = build("calendar", "v3", credentials=creds)
    # 3. Pre-write dedup: service.events().list(calendarId=GCAL_TARGET_CALENDAR_ID,
    #    timeMin=(start_dt - 1day).isoformat(), timeMax=(start_dt + 1day).isoformat())
    #    → fuzz-match titles
    # 4. service.events().insert(calendarId=..., body={
    #      "summary": candidate.title,
    #      "start": {"dateTime": candidate.start_dt.isoformat()},
    #      "end": {"dateTime": (candidate.end_dt or start_dt + 1h).isoformat()},
    #      "location": candidate.location,
    #      "description": description,
    #    })
    # 5. Return WrittenEvent(gcal_event_id=result["id"], fingerprint=fp, candidate=candidate)

    logger.warning("gcal writer not yet implemented")
    return None
