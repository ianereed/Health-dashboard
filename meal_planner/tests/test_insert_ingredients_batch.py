"""Tests for _insert_ingredients_batch — the never-drop ingestion rewrite (Chunk 2.6 B)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from meal_planner.db import init_db, _get_conn
from meal_planner.seed_from_sheet import _insert_ingredients_batch


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "recipes.db"
    init_db(p)
    with _get_conn(p) as c:
        c.execute(
            "INSERT INTO recipes (title, base_servings, created_at, updated_at) "
            "VALUES ('Test', 4, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
    return p


def _recipe_id(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    rid = conn.execute("SELECT id FROM recipes LIMIT 1").fetchone()[0]
    conn.close()
    return rid


def _rows(db_path: Path, recipe_id: int) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM ingredients WHERE recipe_id=? ORDER BY sort_order", (recipe_id,)
    ).fetchall()
    conn.close()
    return rows


def test_clean_numeric_qtys(db_path):
    rid = _recipe_id(db_path)
    parsed = [
        {"name": "oil", "qty": 1, "unit": "tbsp"},
        {"name": "flour", "qty": 2.0, "unit": "cup"},
    ]
    count, warnings = _insert_ingredients_batch(
        recipe_id=rid, parsed=parsed, base_servings=4, path=db_path
    )
    assert count == 2
    assert warnings == []
    rows = _rows(db_path, rid)
    assert rows[0]["qty_per_serving"] == pytest.approx(0.25)
    assert rows[0]["qty_raw"] == "1"
    assert rows[1]["qty_per_serving"] == pytest.approx(0.5)
    assert rows[1]["qty_raw"] == "2.0"


def test_string_fraction_qty(db_path):
    rid = _recipe_id(db_path)
    parsed = [{"name": "salt", "qty": "1/4", "unit": "tsp"}]
    count, warnings = _insert_ingredients_batch(
        recipe_id=rid, parsed=parsed, base_servings=4, path=db_path
    )
    assert count == 1
    assert warnings == []
    rows = _rows(db_path, rid)
    assert rows[0]["qty_per_serving"] == pytest.approx(0.0625)
    assert rows[0]["qty_raw"] == "1/4"


def test_compound_qty_preserved_with_warning(db_path):
    rid = _recipe_id(db_path)
    parsed = [{"name": "flour", "qty": "1/4 cup plus 2 tablespoons"}]
    count, warnings = _insert_ingredients_batch(
        recipe_id=rid, parsed=parsed, base_servings=4, path=db_path
    )
    assert count == 1
    assert len(warnings) == 1
    rows = _rows(db_path, rid)
    assert rows[0]["qty_per_serving"] is None
    assert rows[0]["qty_raw"] == "1/4 cup plus 2 tablespoons"


def test_to_taste_qty(db_path):
    rid = _recipe_id(db_path)
    parsed = [{"name": "pepper", "qty": "to taste"}]
    count, warnings = _insert_ingredients_batch(
        recipe_id=rid, parsed=parsed, base_servings=4, path=db_path
    )
    assert count == 1
    assert len(warnings) == 1
    rows = _rows(db_path, rid)
    assert rows[0]["qty_per_serving"] is None
    assert rows[0]["qty_raw"] == "to taste"


def test_qty_empty_string(db_path):
    rid = _recipe_id(db_path)
    parsed = [{"name": "egg", "qty": "  "}]
    count, warnings = _insert_ingredients_batch(
        recipe_id=rid, parsed=parsed, base_servings=4, path=db_path
    )
    assert count == 1
    assert warnings == []
    rows = _rows(db_path, rid)
    assert rows[0]["qty_per_serving"] is None
    assert rows[0]["qty_raw"] is None


def test_empty_name_skipped(db_path):
    rid = _recipe_id(db_path)
    parsed = [{"name": "  ", "qty": 1}]
    count, warnings = _insert_ingredients_batch(
        recipe_id=rid, parsed=parsed, base_servings=4, path=db_path
    )
    assert count == 0
    assert warnings == []
    rows = _rows(db_path, rid)
    assert len(rows) == 0


def test_qty_bool_rejected(db_path):
    rid = _recipe_id(db_path)
    parsed = [{"name": "x", "qty": True}]
    count, warnings = _insert_ingredients_batch(
        recipe_id=rid, parsed=parsed, base_servings=4, path=db_path
    )
    assert count == 1
    assert len(warnings) == 1
    rows = _rows(db_path, rid)
    assert rows[0]["qty_per_serving"] is None
    assert rows[0]["qty_raw"] == "True"


def test_qty_dict_rejected(db_path):
    rid = _recipe_id(db_path)
    parsed = [{"name": "x", "qty": {"weird": "thing"}}]
    count, warnings = _insert_ingredients_batch(
        recipe_id=rid, parsed=parsed, base_servings=4, path=db_path
    )
    assert count == 1
    assert len(warnings) == 1
    rows = _rows(db_path, rid)
    assert rows[0]["qty_per_serving"] is None
    assert rows[0]["qty_raw"] == repr({"weird": "thing"})


def test_chicken_pot_pie_replay_no_drops(db_path):
    """Reproduces the live bug: 17 rows in → 17 rows out, 3 compound warnings."""
    rid = _recipe_id(db_path)
    # 17-row fixture: 14 clean qtys from golden.json + 3 deliberately compound
    parsed = [
        {"name": "extra-virgin olive oil", "qty": "1", "unit": "tablespoon"},
        {"name": "boneless, skinless chicken breasts or thighs", "qty": "1", "unit": "pound"},
        {"name": "unsalted butter", "qty": "4", "unit": "tablespoons"},
        {"name": "small carrots, peeled and chopped", "qty": "3", "unit": None},
        {"name": "celery ribs, chopped", "qty": "2", "unit": None},
        {"name": "medium leek, sliced", "qty": "1", "unit": None},
        {"name": "medium garlic", "qty": "3", "unit": "cloves"},
        {"name": "fresh thyme", "qty": "2", "unit": "teaspoons"},
        {"name": "Diamond Crystal kosher salt", "qty": "2", "unit": "teaspoons"},
        {"name": "cayenne pepper", "qty": "1/4", "unit": "teaspoon"},
        # Compound — was the bug trigger
        {"name": "all-purpose flour", "qty": "1/4 cup plus 2 tablespoons", "unit": None},
        {"name": "chicken broth", "qty": "2", "unit": "cups"},
        # Compound — another real-world pattern
        {"name": "heavy cream", "qty": "1/4 cup, plus 1 teaspoon", "unit": None},
        {"name": "frozen sweet green peas", "qty": "1 1/2", "unit": "cups"},
        {"name": "lemon zest", "qty": "2", "unit": "teaspoons"},
        # Compound — vague quantity
        {"name": "puff pastry, thawed", "qty": "scant 1 cup", "unit": None},
        {"name": "large egg", "qty": "1", "unit": None},
    ]
    count, warnings = _insert_ingredients_batch(
        recipe_id=rid, parsed=parsed, base_servings=4, path=db_path
    )
    assert count == 17, f"expected 17 rows inserted, got {count}"
    assert len(warnings) == 3, f"expected 3 warnings, got {warnings}"

    conn = sqlite3.connect(str(db_path))
    db_count = conn.execute(
        "SELECT COUNT(*) FROM ingredients WHERE recipe_id=?", (rid,)
    ).fetchone()[0]
    conn.close()
    assert db_count == 17


def test_warnings_format(db_path):
    rid = _recipe_id(db_path)
    parsed = [
        {"name": "a", "qty": "compound stuff"},
        {"name": "b", "qty": "also compound"},
    ]
    _, warnings = _insert_ingredients_batch(
        recipe_id=rid, parsed=parsed, base_servings=4, path=db_path
    )
    assert len(warnings) == 2
    assert warnings[0].startswith("row 0:")
    assert warnings[1].startswith("row 1:")
