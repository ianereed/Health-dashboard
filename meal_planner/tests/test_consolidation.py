"""Snapshot regression tests for meal_planner.consolidation.

All HTTP (Gemini) is mocked — no live API calls. Tests assert the
consolidate_for_grocery() → GroceryLine[] pipeline given canned Gemini
responses.
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

from meal_planner.db import init_db, insert_ingredient, insert_recipe
from meal_planner.models import GroceryLine, Recipe
from meal_planner.queries import get_recipe
from meal_planner.consolidation import consolidate_for_grocery


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "recipes.db"
    init_db(p)
    return p


def _make_recipe(db_path: Path, title: str = "Test Recipe", base_servings: int = 4) -> Recipe:
    rid = insert_recipe(title=title, base_servings=base_servings, path=db_path)
    return get_recipe(rid, path=db_path)


def _add_ingredient(db_path: Path, recipe_id: int, name: str, qty: float | None, unit: str | None, todoist_section: str | None = None) -> None:
    insert_ingredient(
        recipe_id=recipe_id,
        name=name,
        qty_per_serving=qty,
        unit=unit,
        todoist_section=todoist_section,
        path=db_path,
    )


def _make_gemini_resp(items: list[dict]) -> object:
    """Return a fake requests.Response for a Gemini success."""
    class FakeResp:
        status_code = 200

        def json(self) -> dict:
            text = json.dumps(items)
            return {
                "candidates": [
                    {"content": {"parts": [{"text": text}]}}
                ]
            }

        @property
        def text(self) -> str:
            return json.dumps(self.json())

    return FakeResp()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

SECTIONS = ["Produce", "Dairy", "Pantry", "Meat", "Frozen", "Other"]


def test_happy_path_consolidates_duplicates(monkeypatch, db_path: Path) -> None:
    """Two recipes each with olive oil → Gemini merges → one GroceryLine."""
    r1 = _make_recipe(db_path, "Pasta", base_servings=4)
    _add_ingredient(db_path, r1.id, "olive oil", 0.25, "cup", "Pantry")  # 1 cup at 4 servings

    r2 = _make_recipe(db_path, "Salad", base_servings=2)
    _add_ingredient(db_path, r2.id, "olive oil", 0.5, "cup", "Pantry")  # 1 cup at 2 servings

    canned = [{"name": "olive oil", "qty": 2.0, "unit": "cup", "section": "Pantry"}]
    monkeypatch.setattr("meal_planner.consolidation.requests.post", lambda *a, **kw: _make_gemini_resp(canned))

    result = consolidate_for_grocery(
        [(r1, 4), (r2, 2)],
        sections=SECTIONS,
        api_key="test-key",
        path=db_path,
    )
    assert len(result) == 1
    assert result[0].name == "olive oil"
    assert result[0].qty == pytest.approx(2.0)
    assert result[0].unit == "cup"
    assert result[0].todoist_section == "Pantry"


def test_section_drift_falls_back_to_first(monkeypatch, db_path: Path, capsys) -> None:
    """Unknown section from Gemini → falls back to sections[0] with a stderr WARN."""
    r = _make_recipe(db_path)
    _add_ingredient(db_path, r.id, "flour", 0.5, "cup")

    canned = [{"name": "flour", "qty": 2.0, "unit": "cup", "section": "Bakery"}]
    monkeypatch.setattr("meal_planner.consolidation.requests.post", lambda *a, **kw: _make_gemini_resp(canned))

    result = consolidate_for_grocery(
        [(r, 4)],
        sections=SECTIONS,
        api_key="test-key",
        path=db_path,
    )
    assert len(result) == 1
    assert result[0].todoist_section == SECTIONS[0]  # fallback to first

    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "Bakery" in captured.err


def test_unparseable_gemini_response_returns_empty(monkeypatch, db_path: Path) -> None:
    """Gemini returns text with no JSON array → returns [] without raising."""
    r = _make_recipe(db_path)
    _add_ingredient(db_path, r.id, "salt", None, None)

    class BadResp:
        status_code = 200

        def json(self) -> dict:
            return {"candidates": [{"content": {"parts": [{"text": "Sorry, I cannot help."}]}}]}

        @property
        def text(self) -> str:
            return "Sorry, I cannot help."

    monkeypatch.setattr("meal_planner.consolidation.requests.post", lambda *a, **kw: BadResp())

    result = consolidate_for_grocery(
        [(r, 4)],
        sections=SECTIONS,
        api_key="test-key",
        path=db_path,
    )
    assert result == []


def test_dropped_data_warn(monkeypatch, db_path: Path, capsys) -> None:
    """10 input lines, Gemini returns 2 → stderr WARN about dropped data."""
    r = _make_recipe(db_path, base_servings=1)
    for i in range(10):
        _add_ingredient(db_path, r.id, f"ingredient_{i}", float(i + 1), "g")

    canned = [
        {"name": "ingredient_0", "qty": 1.0, "unit": "g", "section": "Pantry"},
        {"name": "ingredient_1", "qty": 2.0, "unit": "g", "section": "Pantry"},
    ]
    monkeypatch.setattr("meal_planner.consolidation.requests.post", lambda *a, **kw: _make_gemini_resp(canned))

    result = consolidate_for_grocery(
        [(r, 1)],
        sections=SECTIONS,
        api_key="test-key",
        path=db_path,
    )
    assert len(result) == 2
    captured = capsys.readouterr()
    assert "WARN" in captured.err


def test_qty_null_for_uncountable(monkeypatch, db_path: Path) -> None:
    """Gemini returns qty=null for 'salt to taste' → GroceryLine.qty is None."""
    r = _make_recipe(db_path)
    _add_ingredient(db_path, r.id, "salt", None, None)

    canned = [{"name": "salt", "qty": None, "unit": "", "section": "Pantry"}]
    monkeypatch.setattr("meal_planner.consolidation.requests.post", lambda *a, **kw: _make_gemini_resp(canned))

    result = consolidate_for_grocery(
        [(r, 4)],
        sections=SECTIONS,
        api_key="test-key",
        path=db_path,
    )
    assert len(result) == 1
    assert result[0].qty is None
    assert result[0].name == "salt"
