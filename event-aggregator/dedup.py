"""
Deduplication logic for candidate events.

Two events are considered duplicates if:
  1. Fingerprints match (sha256 of normalized title + YYYY-MM-DDTHH), OR
  2. fuzz.ratio(title_a, title_b) > 85 AND start times within 60 minutes

The fingerprint includes an hour bucket so a 2pm and a 4pm event with the
same title get distinct fingerprints; rule (2) handles legitimate duplicates
that drift across the hour boundary.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Union

from thefuzz import fuzz

from models import CandidateEvent, CandidateTodo

_FUZZY_THRESHOLD = 85
_TIME_WINDOW = timedelta(minutes=60)
_RECENT_WINDOW = timedelta(days=30)


@dataclass(frozen=True)
class EventKey:
    """Lightweight (title, start_dt) pair for cross-run dedup checks."""
    title: str
    start_dt: datetime


def fingerprint(event: CandidateEvent) -> str:
    """Stable fingerprint: sha256(normalized_title + YYYY-MM-DDTHH).

    Hour-bucketed so an event rescheduled to a different hour produces a
    different fingerprint, but minute-level jitter from LLM extraction does
    not break cross-source dedup.
    """
    key = event.title.lower().strip() + event.start_dt.strftime("%Y-%m-%dT%H")
    return hashlib.sha256(key.encode()).hexdigest()


def todo_fingerprint(todo: CandidateTodo) -> str:
    """Stable fingerprint: sha256(normalized_title + source + source_id).
    Deduplicates the same todo extracted from the same message across runs."""
    key = todo.title.lower().strip() + todo.source + todo.source_id
    return hashlib.sha256(key.encode()).hexdigest()


def is_duplicate(
    candidate: CandidateEvent,
    existing_events: Iterable[Union[CandidateEvent, EventKey]],
) -> bool:
    """
    Return True if candidate is a duplicate of any event in existing_events.
    Existing entries may be CandidateEvent or EventKey tuples (lighter shape
    used for state-derived lookups).
    """
    fp = fingerprint(candidate)
    cand_lower = candidate.title.lower()
    for existing in existing_events:
        time_diff = abs(candidate.start_dt - existing.start_dt)
        if time_diff > _TIME_WINDOW:
            continue
        # Reconstruct the existing fingerprint without requiring a full CandidateEvent
        if isinstance(existing, CandidateEvent):
            if fingerprint(existing) == fp:
                return True
        else:
            existing_fp = hashlib.sha256(
                (existing.title.lower().strip() + existing.start_dt.strftime("%Y-%m-%dT%H")).encode()
            ).hexdigest()
            if existing_fp == fp:
                return True
        if fuzz.ratio(cand_lower, existing.title.lower()) > _FUZZY_THRESHOLD:
            return True
    return False


def persisted_events(state, days: int = 30) -> list[EventKey]:
    """
    Build a lightweight list of recent + upcoming known events from state
    for cross-run fuzzy dedup. Includes:
      - `written_events` whose start_dt is within the last `days` days OR in
        the future (most are upcoming; the lookback catches re-extractions
        of recently-past events from new sources)
      - pending proposal items still awaiting a click
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    out: list[EventKey] = []

    for info in state.get_written_events().values():
        start_iso = info.get("start")
        if not start_iso:
            continue
        try:
            start_dt = datetime.fromisoformat(start_iso)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if start_dt >= cutoff:
            out.append(EventKey(title=info.get("title", ""), start_dt=start_dt))

    for batch in state._data.get("pending_proposals", []):
        for item in batch.get("items", []):
            if item.get("status") != "pending":
                continue
            start_iso = item.get("start_dt")
            if not start_iso:
                continue
            try:
                start_dt = datetime.fromisoformat(start_iso)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            out.append(EventKey(title=item.get("title", ""), start_dt=start_dt))

    return out
