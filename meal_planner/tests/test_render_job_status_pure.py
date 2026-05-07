"""Tests for _format_status — the pure result-dict → (level, message) formatter.

Covers the six cases documented in the Chunk C plan:
  1. all-sent → success
  2. partial-sent (sent < attempted) → warning
  3. error key set → error
  4. consolidate_failed set → error
  5. consolidate_dropped > 0 with sent == attempted → warning
  6. non-dict result → error
"""
from __future__ import annotations

import pytest


def _fmt(result):
    from console.tabs.plan import _format_status
    return _format_status(result)


# ---------------------------------------------------------------------------
# send-to-todoist shaped results
# ---------------------------------------------------------------------------

def test_all_sent_success() -> None:
    result = {"items_sent": 3, "items_attempted": 3, "consolidate_failed": None, "consolidate_dropped": 0, "error": None}
    level, msg = _fmt(result)
    assert level == "success"
    assert "3/3" in msg


def test_partial_sent_warning() -> None:
    result = {"items_sent": 2, "items_attempted": 3, "consolidate_failed": None, "consolidate_dropped": 0, "error": None}
    level, msg = _fmt(result)
    assert level == "warning"
    assert "2/3" in msg


def test_error_key_set_returns_error() -> None:
    result = {"items_sent": 0, "items_attempted": 2, "consolidate_failed": None, "consolidate_dropped": 0, "error": "TODOIST_API_TOKEN not set"}
    level, msg = _fmt(result)
    assert level == "error"
    assert "failed" in msg.lower()


def test_consolidate_failed_returns_error() -> None:
    result = {"items_sent": 3, "items_attempted": 3, "consolidate_failed": "rate_limit", "consolidate_dropped": 0, "error": None}
    level, msg = _fmt(result)
    assert level == "error"
    assert "failed" in msg.lower()


def test_consolidate_dropped_with_full_send_warning() -> None:
    result = {"items_sent": 3, "items_attempted": 3, "consolidate_failed": None, "consolidate_dropped": 2, "error": None}
    level, msg = _fmt(result)
    assert level == "warning"
    assert "consolidated-out" in msg


def test_non_dict_result_error() -> None:
    level, msg = _fmt("some unexpected string")
    assert level == "error"
    assert "unexpected" in msg.lower()


# ---------------------------------------------------------------------------
# clear-todoist shaped results
# ---------------------------------------------------------------------------

def test_clear_success() -> None:
    result = {"items_cleared": 5, "error": None}
    level, msg = _fmt(result)
    assert level == "success"
    assert "5/5" in msg


def test_clear_error() -> None:
    result = {"items_cleared": 3, "error": "2 task(s) failed to delete"}
    level, msg = _fmt(result)
    assert level == "error"
    assert "failed" in msg.lower()


def test_none_result_error() -> None:
    level, msg = _fmt(None)
    assert level == "error"
    assert "unexpected" in msg.lower()
