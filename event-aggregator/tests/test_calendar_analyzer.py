"""
Unit tests for calendar_analyzer.py — pure logic, no API calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from analyzers.calendar_analyzer import CalendarEvent, analyze


def _event(
    title: str,
    start: datetime,
    end: datetime | None = None,
    location: str | None = None,
) -> CalendarEvent:
    return CalendarEvent(
        gcal_id=f"mock_{title[:8]}",
        title=title,
        start_dt=start,
        end_dt=end or start + timedelta(hours=1),
        location=location,
        source_description="",
    )


_BASE = datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc)


class TestConflictDetection:
    def test_exact_overlap(self):
        a = _event("Meeting A", _BASE, _BASE + timedelta(hours=2))
        b = _event("Meeting B", _BASE + timedelta(hours=1), _BASE + timedelta(hours=3))
        result = analyze([a, b])
        overlaps = [c for c in result.conflicts if c.conflict_type == "overlap"]
        assert len(overlaps) == 1

    def test_travel_risk(self):
        a = _event("Meeting A", _BASE, _BASE + timedelta(hours=1), location="Downtown Office")
        b = _event("Meeting B", _BASE + timedelta(minutes=75), end=None, location="Airport Terminal 2")
        result = analyze([a, b])
        travel = [c for c in result.conflicts if c.conflict_type == "travel_risk"]
        assert len(travel) == 1

    def test_same_location_no_travel_risk(self):
        a = _event("Meeting A", _BASE, _BASE + timedelta(hours=1), location="Conference Room B")
        b = _event("Meeting B", _BASE + timedelta(minutes=70), end=None, location="Conference Room B")
        result = analyze([a, b])
        travel = [c for c in result.conflicts if c.conflict_type == "travel_risk"]
        assert len(travel) == 0

    def test_no_conflicts_when_spaced(self):
        a = _event("Morning Meeting", _BASE, _BASE + timedelta(hours=1))
        b = _event("Afternoon Meeting", _BASE + timedelta(hours=3))
        result = analyze([a, b])
        assert len(result.conflicts) == 0


class TestLocationClustering:
    def test_same_venue_grouped(self):
        a = _event("Lunch", _BASE, location="Rosewood Cafe Downtown")
        b = _event("Coffee", _BASE + timedelta(days=1), location="Rosewood Cafe Downtown")
        result = analyze([a, b])
        assert len(result.location_clusters) == 1
        assert len(result.location_clusters[0].events) == 2

    def test_different_venues_separate(self):
        a = _event("Lunch", _BASE, location="Rosewood Cafe")
        b = _event("Meeting", _BASE + timedelta(hours=4), location="City Hall Auditorium")
        result = analyze([a, b])
        assert len(result.location_clusters) == 2
