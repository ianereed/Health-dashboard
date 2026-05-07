"""Phase 14.8 — tests for meal_planner_clear_todoist Job kind.

Key invariants under test:
  - Every list request uses label=meal-planner (the safety constant).
  - Only task IDs returned by the labeled list are deleted.
  - An unfiltered task list is never iterated.
  - Per-task failures are collected; the kind does not abort on first failure.
  - Return dict has the correct shape: {"items_cleared": int, "error": str | None}.
  - Pagination (next_cursor) is followed until exhausted.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

import requests as _requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOKEN = "test-token"

_TASK_IDS = ["task-1", "task-2", "task-3"]


def _list_resp(task_ids: list[str], next_cursor: str | None = None):
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "results": [{"id": tid} for tid in task_ids],
        "next_cursor": next_cursor,
    }
    return mock


def _delete_resp(status_code: int = 204):
    mock = MagicMock()
    mock.status_code = status_code
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_list_request_uses_meal_planner_label(monkeypatch):
    """GET /tasks must include label=meal-planner; never an unfiltered list."""
    monkeypatch.setenv("TODOIST_API_TOKEN", _TOKEN)

    captured_get_params: list[dict] = []

    def fake_get(url, headers, params, timeout):
        captured_get_params.append(params)
        return _list_resp([])

    monkeypatch.setattr(_requests, "get", fake_get)
    monkeypatch.setattr(_requests, "delete", lambda *a, **kw: _delete_resp())

    from jobs.kinds.meal_planner_clear_todoist import meal_planner_clear_todoist
    result = meal_planner_clear_todoist()
    out = result(blocking=True, timeout=5)

    assert len(captured_get_params) == 1
    assert captured_get_params[0]["label"] == "meal-planner"


def test_only_labeled_task_ids_are_deleted(monkeypatch):
    """DELETE is called once per task returned by the labeled list, no more."""
    monkeypatch.setenv("TODOIST_API_TOKEN", _TOKEN)

    deleted_ids: list[str] = []

    def fake_get(url, headers, params, timeout):
        return _list_resp(_TASK_IDS)

    def fake_delete(url, headers, timeout):
        task_id = url.split("/")[-1]
        deleted_ids.append(task_id)
        return _delete_resp(204)

    monkeypatch.setattr(_requests, "get", fake_get)
    monkeypatch.setattr(_requests, "delete", fake_delete)

    from jobs.kinds.meal_planner_clear_todoist import meal_planner_clear_todoist
    result = meal_planner_clear_todoist()
    out = result(blocking=True, timeout=5)

    assert sorted(deleted_ids) == sorted(_TASK_IDS)
    assert out["items_cleared"] == 3
    assert out["error"] is None


def test_failure_collected_not_abort(monkeypatch):
    """A failed DELETE does not abort the remaining deletions."""
    monkeypatch.setenv("TODOIST_API_TOKEN", _TOKEN)

    call_order: list[str] = []

    def fake_get(url, headers, params, timeout):
        return _list_resp(["id-a", "id-b", "id-c"])

    def fake_delete(url, headers, timeout):
        task_id = url.split("/")[-1]
        call_order.append(task_id)
        # Fail only the second task
        return _delete_resp(500 if task_id == "id-b" else 204)

    monkeypatch.setattr(_requests, "get", fake_get)
    monkeypatch.setattr(_requests, "delete", fake_delete)

    from jobs.kinds.meal_planner_clear_todoist import meal_planner_clear_todoist
    result = meal_planner_clear_todoist()
    out = result(blocking=True, timeout=5)

    # All three deletes must have been attempted
    assert "id-a" in call_order
    assert "id-b" in call_order
    assert "id-c" in call_order

    assert out["items_cleared"] == 2
    assert out["error"] is not None
    assert "1" in out["error"]


def test_return_dict_shape(monkeypatch):
    """Return dict must contain: items_cleared (int) and error (str | None)."""
    monkeypatch.setenv("TODOIST_API_TOKEN", _TOKEN)

    monkeypatch.setattr(_requests, "get", lambda *a, **kw: _list_resp([]))
    monkeypatch.setattr(_requests, "delete", lambda *a, **kw: _delete_resp())

    from jobs.kinds.meal_planner_clear_todoist import meal_planner_clear_todoist
    result = meal_planner_clear_todoist()
    out = result(blocking=True, timeout=5)

    assert "items_cleared" in out
    assert "error" in out


def test_pagination_follows_next_cursor(monkeypatch):
    """If next_cursor is returned, subsequent requests include cursor= param."""
    monkeypatch.setenv("TODOIST_API_TOKEN", _TOKEN)

    get_calls: list[dict] = []
    responses = [
        _list_resp(["page1-task"], next_cursor="cursor-abc"),
        _list_resp(["page2-task"], next_cursor=None),
    ]
    call_index = [0]

    def fake_get(url, headers, params, timeout):
        get_calls.append(params.copy())
        resp = responses[call_index[0]]
        call_index[0] += 1
        return resp

    deleted_ids: list[str] = []

    def fake_delete(url, headers, timeout):
        deleted_ids.append(url.split("/")[-1])
        return _delete_resp(204)

    monkeypatch.setattr(_requests, "get", fake_get)
    monkeypatch.setattr(_requests, "delete", fake_delete)

    from jobs.kinds.meal_planner_clear_todoist import meal_planner_clear_todoist
    result = meal_planner_clear_todoist()
    out = result(blocking=True, timeout=5)

    assert len(get_calls) == 2
    assert get_calls[0] == {"label": "meal-planner"}
    assert get_calls[1] == {"label": "meal-planner", "cursor": "cursor-abc"}

    assert sorted(deleted_ids) == ["page1-task", "page2-task"]
    assert out["items_cleared"] == 2
    assert out["error"] is None


def test_empty_todoist_returns_zero_counts(monkeypatch):
    """If no tasks are labeled meal-planner, return deleted=0, failed=0."""
    monkeypatch.setenv("TODOIST_API_TOKEN", _TOKEN)

    monkeypatch.setattr(_requests, "get", lambda *a, **kw: _list_resp([]))
    delete_called = []
    monkeypatch.setattr(_requests, "delete", lambda *a, **kw: delete_called.append(1) or _delete_resp())

    from jobs.kinds.meal_planner_clear_todoist import meal_planner_clear_todoist
    result = meal_planner_clear_todoist()
    out = result(blocking=True, timeout=5)

    assert out == {"items_cleared": 0, "error": None}
    assert delete_called == []


def test_label_constant_is_meal_planner():
    """Sanity: LABEL constant must be 'meal-planner', not configurable."""
    from jobs.kinds.meal_planner_clear_todoist import LABEL
    assert LABEL == "meal-planner"


def test_clear_todoist_returns_full_result_shape(monkeypatch):
    """Result dict has items_cleared (int) and error (None on success)."""
    monkeypatch.setenv("TODOIST_API_TOKEN", _TOKEN)

    monkeypatch.setattr(_requests, "get", lambda *a, **kw: _list_resp(["t-1", "t-2"]))
    monkeypatch.setattr(_requests, "delete", lambda *a, **kw: _delete_resp(204))

    from jobs.kinds.meal_planner_clear_todoist import meal_planner_clear_todoist
    result = meal_planner_clear_todoist()
    out = result(blocking=True, timeout=5)

    assert out["items_cleared"] == 2
    assert out["error"] is None
