"""Tests for meal_planner.seed_from_sheet — everything mocked."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from meal_planner.db import init_db
from meal_planner.seed_from_sheet import (
    _progress_key,
    seed,
)

_SECTIONS = ["Produce", "Dairy", "Meat", "Pantry", "Other"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_worksheet(title: str, values: list[list[str]]) -> MagicMock:
    ws = MagicMock()
    ws.title = title
    ws.get_all_values.return_value = values
    return ws


def _make_spreadsheet(worksheets: list[MagicMock]) -> MagicMock:
    ss = MagicMock()
    ss.worksheets.return_value = worksheets
    return ss


def _canned_parsed_ingredients() -> list[dict]:
    return [
        {"name": "soy sauce", "qty": 2.0, "unit": "tbsp", "notes": "", "todoist_section": "Pantry"},
        {"name": "chicken thighs", "qty": 1.0, "unit": "lb", "notes": "skinless", "todoist_section": "Meat"},
        {"name": "garlic", "qty": 3.0, "unit": "clove", "notes": "minced", "todoist_section": "Produce"},
    ]


def _run_seed(
    db_path: Path,
    worksheets: list[MagicMock],
    parsed_ingredients: list[dict] | None = None,
    done_keys: set[str] | None = None,
) -> tuple[int, int]:
    spreadsheet = _make_spreadsheet(worksheets)
    canned = parsed_ingredients if parsed_ingredients is not None else _canned_parsed_ingredients()

    progress_path = db_path.parent / "seed_progress.json"
    if done_keys:
        progress_path.write_text(json.dumps({"done": sorted(done_keys)}, indent=2))

    with (
        patch("meal_planner.seed_from_sheet._open_sheet", return_value=spreadsheet),
        patch("meal_planner.seed_from_sheet._parse_ingredients", return_value=canned),
    ):
        return seed(
            sheet_id="FAKE_SHEET_ID",
            service_account_path="/fake/creds.json",
            api_key="FAKE_API_KEY",
            section_names=_SECTIONS,
            delay=0,
            db_path=db_path,
            progress_path=progress_path,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "recipes.db"
    init_db(p)
    return p


def test_happy_path_single_recipe(db_path: Path) -> None:
    ws = _make_worksheet("Asian", [
        ["Teriyaki Chicken"],
        ["2 tbsp soy sauce"],
        ["1 lb chicken thighs"],
        ["3 cloves garlic"],
    ])
    seeded, skipped = _run_seed(db_path, [ws])
    assert seeded == 1
    assert skipped == 0

    conn = sqlite3.connect(str(db_path))
    recipe_count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
    ing_count = conn.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0]
    conn.close()

    assert recipe_count == 1
    assert ing_count == 3  # 3 canned parsed ingredients


def test_happy_path_multiple_ingredients_stored_as_per_serving(db_path: Path) -> None:
    ws = _make_worksheet("Asian", [["Teriyaki Chicken"], ["2 tbsp soy sauce"]])
    _run_seed(db_path, [ws])

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT qty_per_serving FROM ingredients WHERE name = 'soy sauce'"
    ).fetchone()
    conn.close()
    # qty=2.0 / base_servings=4 = 0.5
    assert row is not None
    assert abs(row[0] - 0.5) < 1e-9


def test_resumability_skips_already_seeded(db_path: Path) -> None:
    ws = _make_worksheet("Asian", [["Teriyaki Chicken"], ["2 tbsp soy sauce"]])
    already_done = {_progress_key("Asian", 0)}
    seeded, skipped = _run_seed(db_path, [ws], done_keys=already_done)
    assert seeded == 0
    assert skipped == 1

    conn = sqlite3.connect(str(db_path))
    recipe_count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
    conn.close()
    assert recipe_count == 0  # nothing written


def test_tag_normalization_tab_name_lowercased(db_path: Path) -> None:
    ws = _make_worksheet("Asian", [["Teriyaki Chicken"], ["2 tbsp soy sauce"]])
    _run_seed(db_path, [ws])

    conn = sqlite3.connect(str(db_path))
    tag_name = conn.execute("SELECT name FROM tags LIMIT 1").fetchone()[0]
    conn.close()
    assert tag_name == "asian"


def test_failed_ingredient_parse_skips_recipe(db_path: Path) -> None:
    ws = _make_worksheet("Italian", [["Pasta"], ["some ingredient"]])
    spreadsheet = _make_spreadsheet([ws])

    with (
        patch("meal_planner.seed_from_sheet._open_sheet", return_value=spreadsheet),
        patch("meal_planner.seed_from_sheet._parse_ingredients", return_value=None),
    ):
        seeded, skipped = seed(
            sheet_id="FAKE",
            service_account_path="/fake/creds.json",
            api_key="FAKE",
            section_names=_SECTIONS,
            delay=0,
            db_path=db_path,
            progress_path=db_path.parent / "seed_progress.json",
        )

    assert seeded == 0
    assert skipped == 1
    conn = sqlite3.connect(str(db_path))
    assert conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == 0
    conn.close()


def test_readme_tab_skipped(db_path: Path) -> None:
    ws_readme = _make_worksheet("readme", [["Some Recipe"], ["ingredient"]])
    ws_real = _make_worksheet("Asian", [["Stir Fry"], ["2 tbsp soy sauce"]])
    seeded, _ = _run_seed(db_path, [ws_readme, ws_real])
    assert seeded == 1  # only the Asian tab processed

    conn = sqlite3.connect(str(db_path))
    titles = [r[0] for r in conn.execute("SELECT title FROM recipes").fetchall()]
    conn.close()
    assert titles == ["Stir Fry"]


def test_multiple_recipes_in_one_tab(db_path: Path) -> None:
    ws = _make_worksheet("Asian", [
        ["Recipe A", "Recipe B"],
        ["1 cup water", "2 tbsp oil"],
        ["", "1 tsp salt"],
    ])
    seeded, _ = _run_seed(db_path, [ws])
    assert seeded == 2

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
    conn.close()
    assert count == 2


def test_single_transaction_no_orphan_on_batch_failure(db_path: Path) -> None:
    """If _insert_ingredients_batch raises, no recipe row should land (A2 regression)."""
    ws = _make_worksheet("Asian", [["Teriyaki Chicken"], ["2 tbsp soy sauce"]])
    spreadsheet = _make_spreadsheet([ws])

    with (
        patch("meal_planner.seed_from_sheet._open_sheet", return_value=spreadsheet),
        patch("meal_planner.seed_from_sheet._parse_ingredients", return_value=_canned_parsed_ingredients()),
        patch(
            "meal_planner.seed_from_sheet._insert_ingredients_batch",
            side_effect=RuntimeError("simulated batch failure"),
        ),
    ):
        seeded, skipped = seed(
            sheet_id="FAKE",
            service_account_path="/fake/creds.json",
            api_key="FAKE",
            section_names=_SECTIONS,
            delay=0,
            db_path=db_path,
            progress_path=db_path.parent / "seed_progress.json",
        )

    assert seeded == 0
    assert skipped == 1

    conn = sqlite3.connect(str(db_path))
    recipe_count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
    conn.close()
    assert recipe_count == 0, "orphaned recipe row must not persist after batch failure"
