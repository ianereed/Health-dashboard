"""
Unit tests for writers/google_calendar.write_event — covers all four
WriteOutcome branches (Inserted, Merged, MergeRequired, Skipped) using
a mocked GCal service so no real credentials are needed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import config
from models import CandidateEvent
from writers.google_calendar import (
    Inserted,
    Merged,
    MergeRequired,
    Skipped,
    write_event,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _future_dt(hours: int = 48) -> datetime:
    return _utcnow() + timedelta(hours=hours)


def _make_candidate(
    title: str = "Team Standup",
    hours: int = 48,
    source: str = "gmail",
    location: str | None = None,
    attendees: list[dict] | None = None,
) -> CandidateEvent:
    return CandidateEvent(
        title=title,
        start_dt=_future_dt(hours),
        end_dt=_future_dt(hours + 1),
        location=location,
        confidence=0.85,
        source=source,
        source_id=f"{source}_001",
        source_url=None,
        confidence_band="high",
        suggested_attendees=attendees or [],
        category="work",
    )


def _snapshot_entry(
    title: str,
    start_dt: datetime,
    calendar_id: str,
    location: str | None = None,
    attendees: list[dict] | None = None,
) -> dict:
    return {
        "title": title,
        "start": start_dt.isoformat(),
        "end": (start_dt + timedelta(hours=1)).isoformat(),
        "location": location,
        "source_description": "",
        "is_all_day": False,
        "calendar_id": calendar_id,
        "attendees": attendees or [],
    }


def _mock_service_empty_scan() -> MagicMock:
    """Service that returns no existing events in the live calendar scan."""
    svc = MagicMock()
    svc.events().list().execute.return_value = {"items": []}
    svc.events().insert().execute.return_value = {"id": "evt_new_123"}
    return svc


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestWriteEventInserted:
    """Empty snapshot + empty live scan → new event created → Inserted."""

    def test_inserted_returns_inserted_outcome(self):
        candidate = _make_candidate()
        svc = _mock_service_empty_scan()

        with patch("writers.google_calendar._get_service", return_value=svc):
            outcome = write_event(candidate, snapshot={})

        assert isinstance(outcome, Inserted), f"Expected Inserted, got {outcome!r}"
        assert outcome.written.gcal_event_id == "evt_new_123"
        assert outcome.written.candidate is candidate

    def test_inserted_calls_events_insert(self):
        candidate = _make_candidate(title="Birthday Party")
        svc = _mock_service_empty_scan()

        with patch("writers.google_calendar._get_service", return_value=svc):
            write_event(candidate, snapshot={})

        # Find the real insert call (the one with calendarId kwarg)
        insert_calls = [
            c for c in svc.events().insert.call_args_list
            if c.kwargs.get("calendarId")
        ]
        assert len(insert_calls) == 1
        call_kwargs = insert_calls[0].kwargs
        assert call_kwargs["calendarId"] == config.GCAL_WEEKEND_CALENDAR_ID
        assert "Birthday Party" in call_kwargs["body"]["summary"]

    def test_inserted_no_snapshot_still_inserts(self):
        """write_event with snapshot=None falls through to live scan + insert."""
        candidate = _make_candidate()
        svc = _mock_service_empty_scan()

        with patch("writers.google_calendar._get_service", return_value=svc):
            outcome = write_event(candidate, snapshot=None)

        assert isinstance(outcome, Inserted)


class TestWriteEventMerged:
    """Snapshot match on weekend + candidate adds location → Merged (silent patch)."""

    def test_merged_when_weekend_match_has_new_location(self):
        candidate = _make_candidate(title="Team Standup", location="Conference Room A")
        start = candidate.start_dt

        snapshot = {
            "weekend_evt_001": _snapshot_entry(
                title="Team Standup",
                start_dt=start,
                calendar_id=config.GCAL_WEEKEND_CALENDAR_ID,
                location=None,  # no location yet
            )
        }

        svc = MagicMock()
        # _patch_with_additions calls service.events().get() then .patch()
        svc.events().get().execute.return_value = {"description": ""}
        svc.events().patch().execute.return_value = {}

        with patch("writers.google_calendar._get_service", return_value=svc):
            outcome = write_event(candidate, snapshot=snapshot)

        assert isinstance(outcome, Merged), f"Expected Merged, got {outcome!r}"
        assert outcome.matched_title == "Team Standup"
        assert outcome.gcal_event_id == "weekend_evt_001"
        assert "location" in outcome.additions

    def test_no_merge_when_weekend_match_has_nothing_new(self):
        """Weekend match with no new fields → Skipped, not Merged."""
        candidate = _make_candidate(title="Team Standup", location=None)
        start = candidate.start_dt

        snapshot = {
            "weekend_evt_002": _snapshot_entry(
                title="Team Standup",
                start_dt=start,
                calendar_id=config.GCAL_WEEKEND_CALENDAR_ID,
                location="Already has a location",
            )
        }

        with patch("writers.google_calendar._get_service", return_value=MagicMock()):
            outcome = write_event(candidate, snapshot=snapshot)

        assert isinstance(outcome, Skipped)
        assert outcome.reason == "weekend_duplicate"


class TestWriteEventMergeRequired:
    """Snapshot match on primary + candidate has new info → MergeRequired."""

    def test_merge_required_when_primary_match_has_new_attendees(self):
        attendees = [{"name": "Alice", "email": "alice@example.com"}]
        candidate = _make_candidate(title="Product Review", attendees=attendees)
        start = candidate.start_dt

        snapshot = {
            "primary_evt_001": _snapshot_entry(
                title="Product Review",
                start_dt=start,
                calendar_id=config.GCAL_PRIMARY_CALENDAR_ID,
                attendees=[],  # no attendees yet
            )
        }

        with patch("writers.google_calendar._get_service", return_value=MagicMock()):
            outcome = write_event(candidate, snapshot=snapshot)

        assert isinstance(outcome, MergeRequired), f"Expected MergeRequired, got {outcome!r}"
        assert outcome.matched_title == "Product Review"
        assert outcome.gcal_event_id == "primary_evt_001"
        assert "attendees" in outcome.additions

    def test_primary_duplicate_with_nothing_new_is_skipped(self):
        """Primary match with no new fields → Skipped (not a merge proposal)."""
        candidate = _make_candidate(title="Product Review", location=None, attendees=None)
        start = candidate.start_dt

        snapshot = {
            "primary_evt_002": _snapshot_entry(
                title="Product Review",
                start_dt=start,
                calendar_id=config.GCAL_PRIMARY_CALENDAR_ID,
                location="Already set",
                attendees=[{"name": "Bob", "email": "bob@example.com"}],
            )
        }

        with patch("writers.google_calendar._get_service", return_value=MagicMock()):
            outcome = write_event(candidate, snapshot=snapshot)

        assert isinstance(outcome, Skipped)
        assert outcome.reason == "primary_duplicate"


class TestWriteEventSkipped:
    """Live scan match on weekend (no snapshot) → Skipped(reason="weekend_live_duplicate")."""

    def test_skipped_when_live_scan_finds_weekend_duplicate(self):
        candidate = _make_candidate(title="Team Standup")
        start = candidate.start_dt

        svc = MagicMock()
        svc.events().list().execute.return_value = {
            "items": [
                {
                    "summary": "Team Standup",
                    "start": {"dateTime": start.isoformat()},
                }
            ]
        }

        # snapshot=None forces the live scan path
        with patch("writers.google_calendar._get_service", return_value=svc):
            outcome = write_event(candidate, snapshot=None)

        assert isinstance(outcome, Skipped), f"Expected Skipped, got {outcome!r}"
        assert outcome.reason == "weekend_live_duplicate"

    def test_dry_run_always_returns_skipped(self):
        candidate = _make_candidate()
        with patch("writers.google_calendar._get_service", return_value=MagicMock()):
            outcome = write_event(candidate, dry_run=True, snapshot={})
        assert isinstance(outcome, Skipped)
        assert outcome.reason == "dry_run"
