"""
Event log — appends a JSONL entry and sends a Slack DM for every event created/updated.

The JSONL file (event_log.jsonl, gitignored) is the durable on-disk audit trail.
The Slack DM is the iOS-accessible, searchable, notification-friendly version.

Log entry schema:
  {"ts": "ISO8601", "action": "created|updated", "gcal_id": "...", "title": "...",
   "start": "YYYY-MM-DDTHH:MM:SS+00:00", "source": "gmail|slack|...", "fingerprint": "..."}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from models import WrittenEvent

logger = logging.getLogger(__name__)

LOG_PATH = Path(__file__).parent.parent / "event_log.jsonl"


def record(written: WrittenEvent, action: str = "created") -> None:
    """Append to JSONL log and send Slack DM notification."""
    entry = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "action": action,
        "gcal_id": written.gcal_event_id,
        "title": written.candidate.title,
        "start": written.candidate.start_dt.isoformat(),
        "source": written.candidate.source,
        "fingerprint": written.fingerprint,
    }

    _append_to_log(entry)
    _notify_slack(entry)


def _append_to_log(entry: dict) -> None:
    try:
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        logger.warning("event_log: failed to write to %s: %s", LOG_PATH, exc)


def _notify_slack(entry: dict) -> None:
    """
    Send a Slack DM to SLACK_DIGEST_USER_ID for each created/updated event.
    This is the iOS-accessible audit trail.
    """
    try:
        import config
        if not config.SLACK_BOT_TOKEN or not config.SLACK_DIGEST_USER_ID:
            return

        from slack_sdk import WebClient
        client = WebClient(token=config.SLACK_BOT_TOKEN)

        action_emoji = ":calendar:" if entry["action"] == "created" else ":pencil2:"
        start_str = entry["start"][:16].replace("T", " ")  # "YYYY-MM-DD HH:MM"
        text = (
            f"{action_emoji} *{entry['action'].capitalize()}*: {entry['title']}\n"
            f":clock3: {start_str}  |  :link: source: `{entry['source']}`"
        )

        client.chat_postMessage(channel=config.SLACK_DIGEST_USER_ID, text=text)
    except Exception as exc:
        logger.warning("event_log: Slack notification failed: %s", exc)
