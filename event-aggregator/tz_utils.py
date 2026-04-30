"""
Timezone helpers — one place to ask "what's the user's local now?".

The rule for this codebase:

  - INTERNAL work runs in UTC. Audit-trail timestamps, fingerprints,
    sort keys, watermarks, ISO strings persisted to state.json — all
    stay UTC via `datetime.now(tz=timezone.utc)` or `state._utcnow()`.

  - EXTERNAL output runs in the user's local timezone. Anything that
    will land in an LLM prompt, a Google Calendar field, a Slack
    message, a Todoist task title, or a user-visible dashboard string
    must use `now_user()` / `today_user_str()` so dates and "today"
    references match the user's wall clock.

A single bug from violating this rule (`extractor.py:208` → off-by-one
"tomorrow" resolution every late-evening PT extraction) prompted this
helper. See commit 5e0aff8 for the original symptom.

This module is deliberately stdlib-only and self-contained so each
sister Home-Tools project (`finance-monitor`, `health-dashboard`,
`meal-planner`, `medical-records`, `dispatcher`, `service-monitor`) can
copy it verbatim when audited. A shared library at the repo root would
require coupling six independent venvs for a 25-LOC helper.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config


def now_user() -> datetime:
    """Timezone-aware datetime in the user's local zone (`config.USER_TIMEZONE`)."""
    return datetime.now(tz=ZoneInfo(config.USER_TIMEZONE))


def today_user_str() -> str:
    """User-local calendar date as YYYY-MM-DD."""
    return now_user().strftime("%Y-%m-%d")


def now_utc() -> datetime:
    """Internal-use UTC now. Use for fingerprints, audit trail, watermarks."""
    return datetime.now(tz=timezone.utc)
