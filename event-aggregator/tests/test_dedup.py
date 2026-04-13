"""
Unit tests for dedup.py — pure logic, no external dependencies.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dedup import fingerprint, is_duplicate
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
