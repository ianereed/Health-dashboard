"""Tests for tz_utils helpers — covers the two scenarios that produced
the original bug (late-evening PT, DST spring-forward) plus a sanity
check for tz-awareness."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

import tz_utils


def test_now_user_returns_tz_aware_datetime_in_user_zone():
    dt = tz_utils.now_user()
    assert dt.tzinfo is not None
    # tzinfo can be ZoneInfo("America/Los_Angeles") — its key matches USER_TIMEZONE.
    import config
    assert str(dt.tzinfo) == config.USER_TIMEZONE


def test_today_user_str_matches_zoneinfo_now():
    """Sanity: helper output equals the obvious manual computation."""
    import config
    expected = datetime.now(tz=ZoneInfo(config.USER_TIMEZONE)).strftime("%Y-%m-%d")
    assert tz_utils.today_user_str() == expected


def test_today_user_str_late_evening_boundary(monkeypatch):
    """The literal scenario that produced the original bug:
    19:50 PT on Wed Apr 29 = 02:50 UTC on Thu Apr 30. UTC-naive code
    returned "2026-04-30" and the LLM resolved "tomorrow" to Friday;
    user-tz code must return "2026-04-29" so "tomorrow" lands on Thu."""
    import config
    monkeypatch.setattr(config, "USER_TIMEZONE", "America/Los_Angeles", raising=False)

    fake_now_utc = datetime(2026, 4, 30, 2, 50, 0, tzinfo=timezone.utc)

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fake_now_utc.replace(tzinfo=None)
            return fake_now_utc.astimezone(tz)

    with patch("tz_utils.datetime", FakeDateTime):
        assert tz_utils.today_user_str() == "2026-04-29"


def test_today_user_str_dst_spring_forward(monkeypatch):
    """During DST spring-forward, the wall clock jumps from 01:59 PST
    (UTC-8) to 03:00 PDT (UTC-7). At 02:30 UTC on the morning of
    2026-03-08 it's still Saturday Mar 7 in LA (18:30 PT). ZoneInfo
    handles the offset shift correctly."""
    import config
    monkeypatch.setattr(config, "USER_TIMEZONE", "America/Los_Angeles", raising=False)

    # 2026-03-08 02:30 UTC = 2026-03-07 18:30 PST (still Saturday)
    fake_now_utc = datetime(2026, 3, 8, 2, 30, 0, tzinfo=timezone.utc)

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fake_now_utc.replace(tzinfo=None)
            return fake_now_utc.astimezone(tz)

    with patch("tz_utils.datetime", FakeDateTime):
        assert tz_utils.today_user_str() == "2026-03-07"
