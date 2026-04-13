"""
Persistent state management.

state.json (gitignored) tracks:
- last_run timestamps per source
- seen message IDs for API-based sources (pruned to 30-day rolling window)
- written event fingerprints (pruned once event date has passed)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).parent / "state.json"

_DEFAULT_LOOKBACK_DAYS = 7  # first-run default when no last_run is recorded

ALL_SOURCES = [
    "gmail", "gcal", "slack", "imessage", "whatsapp",
    "discord", "messenger", "instagram",
]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


class State:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    # ── last_run ─────────────────────────────────────────────────────────────

    def last_run(self, source: str) -> datetime:
        """Return last run time for source, defaulting to 7 days ago on first run."""
        raw = self._data.get("last_run", {}).get(source)
        if raw:
            return _parse_dt(raw)
        return _utcnow() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)

    def set_last_run(self, source: str, dt: datetime | None = None) -> None:
        self._data.setdefault("last_run", {})[source] = (dt or _utcnow()).isoformat()

    # ── seen IDs ─────────────────────────────────────────────────────────────

    def is_seen(self, source: str, msg_id: str) -> bool:
        return msg_id in self._data.get("seen_message_ids", {}).get(source, [])

    def mark_seen(self, source: str, msg_id: str) -> None:
        bucket = self._data.setdefault("seen_message_ids", {}).setdefault(source, [])
        if msg_id not in bucket:
            bucket.append(msg_id)

    # ── fingerprints ─────────────────────────────────────────────────────────

    def has_fingerprint(self, fp: str) -> bool:
        return fp in self._data.get("written_fingerprints", [])

    def add_fingerprint(self, fp: str) -> None:
        fps = self._data.setdefault("written_fingerprints", [])
        if fp not in fps:
            fps.append(fp)

    # ── pruning ───────────────────────────────────────────────────────────────

    def prune(self) -> None:
        """Remove stale entries to prevent unbounded growth."""
        cutoff = _utcnow() - timedelta(days=30)

        # Prune seen_message_ids: keep only IDs seen after cutoff.
        # We can't know when an ID was added without a separate timestamp index,
        # so instead we cap each source bucket to the most recent 1000 entries.
        for source in self._data.get("seen_message_ids", {}):
            bucket = self._data["seen_message_ids"][source]
            self._data["seen_message_ids"][source] = bucket[-1000:]

        # Prune fingerprints: format is sha256(title+date), date embedded as YYYY-MM-DD.
        # We can't decode the hash, so keep fingerprints for up to 30 days past last_run.
        # Simple approach: cap to most recent 5000 entries.
        fps = self._data.get("written_fingerprints", [])
        self._data["written_fingerprints"] = fps[-5000:]

        logger.debug("state pruned")


def load() -> State:
    if STATE_PATH.exists():
        with STATE_PATH.open() as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                logger.warning("state.json is corrupt; starting fresh")
                data = {}
    else:
        data = {}
    return State(data)


def save(state: State) -> None:
    state.prune()
    with STATE_PATH.open("w") as f:
        json.dump(state._data, f, indent=2, default=str)
    logger.debug("state saved to %s", STATE_PATH)
