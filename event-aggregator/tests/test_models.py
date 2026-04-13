"""
Unit tests for data model validation logic.
"""
from __future__ import annotations

from datetime import datetime, timezone

from models import CandidateEvent


class TestCandidateEvent:
    def test_confidence_clamped_high(self):
        e = CandidateEvent("Test", datetime(2026, 5, 1, tzinfo=timezone.utc),
                           None, None, confidence=1.5, source="test", source_id="x")
        assert e.confidence == 1.0

    def test_confidence_clamped_low(self):
        e = CandidateEvent("Test", datetime(2026, 5, 1, tzinfo=timezone.utc),
                           None, None, confidence=-0.5, source="test", source_id="x")
        assert e.confidence == 0.0

    def test_title_stripped_and_truncated(self):
        long_title = "A" * 300
        e = CandidateEvent(long_title, datetime(2026, 5, 1, tzinfo=timezone.utc),
                           None, None, confidence=0.9, source="test", source_id="x")
        assert len(e.title) == 200

    def test_title_stripped_whitespace(self):
        e = CandidateEvent("  Team Lunch  ", datetime(2026, 5, 1, tzinfo=timezone.utc),
                           None, None, confidence=0.9, source="test", source_id="x")
        assert e.title == "Team Lunch"
