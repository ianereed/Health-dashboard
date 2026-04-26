"""
Unit tests for dedup.py — pure logic, no external dependencies.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dedup import EventKey, fingerprint, is_duplicate, persisted_events
from models import CandidateEvent


def _event(title: str, start: datetime, location: str | None = None) -> CandidateEvent:
    return CandidateEvent(
        title=title,
        start_dt=start,
        end_dt=None,
        location=location,
        confidence=0.9,
        source="test",
        source_id="test_001",
    )


_BASE = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)


class TestFingerprint:
    def test_same_title_same_date(self):
        a = _event("Team Lunch", _BASE)
        b = _event("Team Lunch", _BASE)
        assert fingerprint(a) == fingerprint(b)

    def test_case_insensitive(self):
        a = _event("team lunch", _BASE)
        b = _event("TEAM LUNCH", _BASE)
        assert fingerprint(a) == fingerprint(b)

    def test_different_dates_differ(self):
        a = _event("Team Lunch", _BASE)
        b = _event("Team Lunch", _BASE + timedelta(days=1))
        assert fingerprint(a) != fingerprint(b)

    def test_different_titles_differ(self):
        a = _event("Team Lunch", _BASE)
        b = _event("Board Meeting", _BASE)
        assert fingerprint(a) != fingerprint(b)

    def test_different_hour_differs(self):
        # Tier 1.5: hour bucket is part of the fingerprint so a reschedule
        # to a different hour produces a distinct fp (paired with fuzzy
        # window for genuine duplicates within the same hour).
        a = _event("Team Lunch", _BASE)
        b = _event("Team Lunch", _BASE.replace(hour=16))
        assert fingerprint(a) != fingerprint(b)

    def test_minute_jitter_same_hour(self):
        a = _event("Team Lunch", _BASE)
        b = _event("Team Lunch", _BASE.replace(minute=45))
        assert fingerprint(a) == fingerprint(b)


class TestIsDuplicate:
    def test_exact_fingerprint_match(self):
        a = _event("Team Lunch", _BASE)
        b = _event("Team Lunch", _BASE)
        assert is_duplicate(a, [b])

    def test_fuzzy_title_close_time(self):
        a = _event("Team Lunch at Rosewood", _BASE)
        b = _event("Team Lunch at Rosewood Cafe", _BASE + timedelta(minutes=30))
        assert is_duplicate(a, [b])

    def test_fuzzy_title_far_time(self):
        a = _event("Team Lunch", _BASE)
        b = _event("Team Lunch", _BASE + timedelta(hours=2))
        assert not is_duplicate(a, [b])

    def test_different_title_no_match(self):
        a = _event("Team Lunch", _BASE)
        b = _event("Board Meeting", _BASE)
        assert not is_duplicate(a, [b])

    def test_empty_existing(self):
        a = _event("Team Lunch", _BASE)
        assert not is_duplicate(a, [])

    def test_eventkey_lightweight_match(self):
        # Tier 1.5: is_duplicate accepts EventKey for state-derived lookups.
        a = _event("Team Lunch", _BASE)
        existing = EventKey(title="team lunch", start_dt=_BASE)
        assert is_duplicate(a, [existing])

    def test_eventkey_fuzzy_within_window(self):
        # Same-event-different-source style: minor wording drift, time within window.
        a = _event("Team Lunch at Rosewood", _BASE)
        existing = EventKey(
            title="Team Lunch at Rosewood Cafe",
            start_dt=_BASE + timedelta(minutes=20),
        )
        assert is_duplicate(a, [existing])
