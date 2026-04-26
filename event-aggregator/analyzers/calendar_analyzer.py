"""
Calendar Intelligence Analyzer

Fetches the full year-ahead calendar and produces:
- Location clusters: groups events by venue (fuzzy-matched)
- Conflict report: exact overlaps and near-misses (< 30 min gap between events at
  different locations, flagged as potential travel-time issues)

Used by the digest notifier and can be run standalone.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from thefuzz import fuzz

logger = logging.getLogger(__name__)

_TRAVEL_WARN_MINUTES = 30  # flag if gap between events at different locations < this
_LOCATION_FUZZY_THRESHOLD = 80  # fuzz.ratio threshold for "same venue"


@dataclass
class CalendarEvent:
    """Lightweight representation of a GCal event for analysis."""
    gcal_id: str
    title: str
    start_dt: datetime
    end_dt: datetime
    location: str | None
    source_description: str  # the "[via event-aggregator | source: X]" description or ""
    is_all_day: bool = False  # True when GCal returned start.date (not start.dateTime)
    calendar_id: str = ""  # which calendar this event lives on (primary vs weekend)
    attendees: list[dict] = field(default_factory=list)  # [{name, email}]


@dataclass
class Conflict:
    event_a: CalendarEvent
    event_b: CalendarEvent
    conflict_type: str  # "overlap" | "travel_risk"
    gap_minutes: float  # negative = overlap duration


@dataclass
class LocationCluster:
    canonical_name: str
    events: list[CalendarEvent] = field(default_factory=list)


@dataclass
class CalendarAnalysis:
    as_of: datetime
    events: list[CalendarEvent]
    conflicts: list[Conflict]
    location_clusters: list[LocationCluster]


def analyze(events: list[CalendarEvent]) -> CalendarAnalysis:
    """
    Given a list of CalendarEvent objects (fetched externally), run full analysis.
    This function is pure — no API calls.
    """
    conflicts = _detect_conflicts(events)
    clusters = _cluster_locations(events)
    return CalendarAnalysis(
        as_of=datetime.now(tz=timezone.utc),
        events=events,
        conflicts=conflicts,
        location_clusters=clusters,
    )


def _detect_conflicts(events: list[CalendarEvent]) -> list[Conflict]:
    conflicts = []
    sorted_events = sorted(events, key=lambda e: e.start_dt)

    for i, a in enumerate(sorted_events):
        for b in sorted_events[i + 1:]:
            if b.start_dt > a.end_dt + timedelta(minutes=_TRAVEL_WARN_MINUTES):
                break  # events are sorted; no further conflicts possible with a

            gap_minutes = (b.start_dt - a.end_dt).total_seconds() / 60

            if gap_minutes < 0:
                # Exact overlap
                conflicts.append(Conflict(a, b, "overlap", gap_minutes))
            elif gap_minutes < _TRAVEL_WARN_MINUTES:
                # Near-miss: check if locations differ
                if a.location and b.location:
                    loc_similarity = fuzz.ratio(
                        a.location.lower(), b.location.lower()
                    )
                    if loc_similarity < _LOCATION_FUZZY_THRESHOLD:
                        conflicts.append(Conflict(a, b, "travel_risk", gap_minutes))

    return conflicts


def _cluster_locations(events: list[CalendarEvent]) -> list[LocationCluster]:
    clusters: list[LocationCluster] = []

    for event in events:
        if not event.location:
            continue
        loc = event.location.strip()
        matched = False
        for cluster in clusters:
            if fuzz.ratio(loc.lower(), cluster.canonical_name.lower()) >= _LOCATION_FUZZY_THRESHOLD:
                cluster.events.append(event)
                matched = True
                break
        if not matched:
            clusters.append(LocationCluster(canonical_name=loc, events=[event]))

    return clusters


def _fetch_calendar(
    service, calendar_id: str, time_min: datetime, time_max: datetime, max_results: int
) -> list[CalendarEvent]:
    """Pull all events on one calendar in [time_min, time_max], tagging each with calendar_id."""
    events: list[CalendarEvent] = []
    page_token: str | None = None
    while True:
        kwargs: dict = {
            "calendarId": calendar_id,
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": max_results,
        }
        if page_token:
            kwargs["pageToken"] = page_token
        result = service.events().list(**kwargs).execute()
        for item in result.get("items", []):
            try:
                ev = _gcal_item_to_event(item)
                ev.calendar_id = calendar_id
                events.append(ev)
            except Exception as exc:
                logger.debug("skipping malformed event %s: %s", item.get("id"), exc)
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return events


def _calendars_to_read() -> list[str]:
    """Return the distinct calendars to read for context + dedup.

    Always includes the primary; adds the weekend calendar if it's a separate
    ID. Deduplicated to keep API calls minimal when both env vars resolve to
    the same value.
    """
    import config
    seen: list[str] = [config.GCAL_PRIMARY_CALENDAR_ID]
    if config.GCAL_WEEKEND_CALENDAR_ID and config.GCAL_WEEKEND_CALENDAR_ID not in seen:
        seen.append(config.GCAL_WEEKEND_CALENDAR_ID)
    return seen


def fetch_year_ahead(service) -> list[CalendarEvent]:
    """
    Fetch all GCal events from today through +365 days, across primary + weekend.
    Each event is tagged with its `calendar_id`.
    """
    now = datetime.now(tz=timezone.utc)
    year_out = now + timedelta(days=365)
    events: list[CalendarEvent] = []
    for cal_id in _calendars_to_read():
        events.extend(_fetch_calendar(service, cal_id, now, year_out, 2500))
    logger.debug(
        "fetch_year_ahead: %d event(s) across %d calendar(s)",
        len(events), len(_calendars_to_read()),
    )
    return events


def fetch_upcoming(service, weeks: int = 4) -> list[CalendarEvent]:
    """
    Fetch GCal events for the next N weeks across primary + weekend.
    Used for injecting calendar context into the Ollama extraction prompt.
    """
    now = datetime.now(tz=timezone.utc)
    horizon = now + timedelta(weeks=weeks)
    events: list[CalendarEvent] = []
    for cal_id in _calendars_to_read():
        events.extend(_fetch_calendar(service, cal_id, now, horizon, 250))
    logger.debug(
        "fetch_upcoming: %d event(s) across %d calendar(s) over next %d weeks",
        len(events), len(_calendars_to_read()), weeks,
    )
    return events


def _gcal_item_to_event(item: dict) -> CalendarEvent:
    # All-day events use `start.date` (YYYY-MM-DD); timed events use `start.dateTime`.
    is_all_day = "dateTime" not in item["start"]
    start_raw = item["start"].get("dateTime") or item["start"].get("date")
    end_raw = item["end"].get("dateTime") or item["end"].get("date")
    start_dt = _parse_gcal_dt(start_raw)
    end_dt = _parse_gcal_dt(end_raw)
    attendees: list[dict] = []
    for a in item.get("attendees") or []:
        if a.get("self"):
            continue  # the user themselves — not a useful merge field
        name = a.get("displayName") or ""
        email = a.get("email") or ""
        if name or email:
            attendees.append({"name": name, "email": email})
    return CalendarEvent(
        gcal_id=item["id"],
        title=item.get("summary", "(no title)"),
        start_dt=start_dt,
        end_dt=end_dt,
        location=item.get("location"),
        source_description=item.get("description", ""),
        is_all_day=is_all_day,
        attendees=attendees,
    )


def _parse_gcal_dt(value: str) -> datetime:
    """Parse a GCal dateTime or date string into a UTC-aware datetime."""
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        # All-day event (date-only string like "2026-04-15") — treat as UTC midnight
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
