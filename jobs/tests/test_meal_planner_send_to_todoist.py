"""Phase 14.5 — tests for meal_planner_send_to_todoist Job kind.

All HTTP (both Gemini consolidation and Todoist create) is mocked.
TODOIST_SECTIONS, TODOIST_API_TOKEN, TODOIST_PROJECT_ID, and GEMINI_API_KEY
are set via monkeypatch.setenv — real .env is never read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from meal_planner.db import init_db, insert_ingredient, insert_recipe
from meal_planner.queries import get_recipe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECTIONS = {"Produce": "sec-prod", "Pantry": "sec-pantry", "Other": "sec-other"}
_SECTIONS_JSON = json.dumps(_SECTIONS)


def _setup_db(db_path: Path) -> int:
    """Create a single recipe with one ingredient in db_path. Returns recipe_id."""
    init_db(db_path)
    rid = insert_recipe(title="Test Pasta", base_servings=4, path=db_path)
    insert_ingredient(
        recipe_id=rid,
        name="olive oil",
        qty_per_serving=0.25,
        unit="cup",
        todoist_section="Pantry",
        path=db_path,
    )
    return rid


class _GeminiResp:
    """Canned Gemini success response returning a single consolidated item."""

    def __init__(self, items: list[dict]) -> None:
        self._items = items

    @property
    def status_code(self) -> int:
        return 200

    def json(self) -> dict:
        return {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(self._items)}]}}
            ]
        }

    @property
    def text(self) -> str:
        return json.dumps(self.json())


class _TodoistResp:
    """Canned Todoist success response."""

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"id": "task-42"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_happy_path_calls_todoist_with_meal_planner_label(monkeypatch, tmp_path: Path) -> None:
    """Captured Todoist payload must have labels == ['meal-planner'], NOT ['event-aggregator']."""
    import meal_planner.db as _db_mod
    db_path = tmp_path / "recipes.db"
    monkeypatch.setattr(_db_mod, "DB_PATH", db_path)
    rid = _setup_db(db_path)

    monkeypatch.setenv("TODOIST_SECTIONS", _SECTIONS_JSON)
    monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")
    monkeypatch.setenv("TODOIST_PROJECT_ID", "proj-1")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    gemini_items = [{"name": "olive oil", "qty": 1.0, "unit": "cup", "section": "Pantry"}]
    todoist_captured: list[dict] = []

    def fake_requests_post(url, *args, **kwargs):
        if "generativelanguage" in url:
            return _GeminiResp(gemini_items)
        # Todoist
        todoist_captured.append(kwargs.get("json") or {})
        return _TodoistResp()

    import requests as _requests
    monkeypatch.setattr(_requests, "post", fake_requests_post)

    from jobs.kinds.meal_planner_send_to_todoist import meal_planner_send_to_todoist
    result = meal_planner_send_to_todoist([[rid, 4]])
    out = result(blocking=True, timeout=5)

    assert out["items_sent"] == 1
    assert out["items_attempted"] == 1
    assert len(todoist_captured) == 1
    assert todoist_captured[0]["labels"] == ["meal-planner"]


def test_section_drift_falls_back_to_first_section(monkeypatch, tmp_path: Path) -> None:
    """Section name from Gemini not in TODOIST_SECTIONS → task uses first section_id."""
    import meal_planner.db as _db_mod
    db_path = tmp_path / "recipes.db"
    monkeypatch.setattr(_db_mod, "DB_PATH", db_path)
    rid = _setup_db(db_path)

    monkeypatch.setenv("TODOIST_SECTIONS", _SECTIONS_JSON)
    monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    # Gemini returns an unknown section name
    gemini_items = [{"name": "olive oil", "qty": 1.0, "unit": "cup", "section": "Bakery"}]
    todoist_captured: list[dict] = []

    def fake_post(url, *args, **kwargs):
        if "generativelanguage" in url:
            return _GeminiResp(gemini_items)
        todoist_captured.append(kwargs.get("json") or {})
        return _TodoistResp()

    import requests as _requests
    monkeypatch.setattr(_requests, "post", fake_post)

    from jobs.kinds.meal_planner_send_to_todoist import meal_planner_send_to_todoist
    result = meal_planner_send_to_todoist([[rid, 4]])
    out = result(blocking=True, timeout=5)

    assert out["items_sent"] == 1
    first_section_id = list(_SECTIONS.values())[0]
    assert todoist_captured[0].get("section_id") == first_section_id


def test_priority_is_string_not_int(monkeypatch, tmp_path: Path) -> None:
    """Priority flows as the string 'normal'; writer maps to int 2 in final payload."""
    import meal_planner.db as _db_mod
    db_path = tmp_path / "recipes.db"
    monkeypatch.setattr(_db_mod, "DB_PATH", db_path)
    rid = _setup_db(db_path)

    monkeypatch.setenv("TODOIST_SECTIONS", _SECTIONS_JSON)
    monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    gemini_items = [{"name": "olive oil", "qty": 1.0, "unit": "cup", "section": "Pantry"}]
    todoist_captured: list[dict] = []

    def fake_post(url, *args, **kwargs):
        if "generativelanguage" in url:
            return _GeminiResp(gemini_items)
        todoist_captured.append(kwargs.get("json") or {})
        return _TodoistResp()

    import requests as _requests
    monkeypatch.setattr(_requests, "post", fake_post)

    from jobs.kinds.meal_planner_send_to_todoist import meal_planner_send_to_todoist
    result = meal_planner_send_to_todoist([[rid, 4]])
    result(blocking=True, timeout=5)

    # _PRIORITY_MAP maps "normal" → 2
    assert todoist_captured[0]["priority"] == 2


def test_returns_items_sent_and_attempted(monkeypatch, tmp_path: Path) -> None:
    """Return dict must have items_sent and items_attempted keys."""
    import meal_planner.db as _db_mod
    db_path = tmp_path / "recipes.db"
    monkeypatch.setattr(_db_mod, "DB_PATH", db_path)
    rid = _setup_db(db_path)

    monkeypatch.setenv("TODOIST_SECTIONS", _SECTIONS_JSON)
    monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    gemini_items = [
        {"name": "olive oil", "qty": 1.0, "unit": "cup", "section": "Pantry"},
        {"name": "garlic", "qty": 3.0, "unit": "cloves", "section": "Produce"},
    ]

    def fake_post(url, *args, **kwargs):
        if "generativelanguage" in url:
            return _GeminiResp(gemini_items)
        return _TodoistResp()

    import requests as _requests
    monkeypatch.setattr(_requests, "post", fake_post)

    from jobs.kinds.meal_planner_send_to_todoist import meal_planner_send_to_todoist
    result = meal_planner_send_to_todoist([[rid, 4]])
    out = result(blocking=True, timeout=5)

    assert "items_sent" in out
    assert "items_attempted" in out
    assert out["items_sent"] == 2
    assert out["items_attempted"] == 2
