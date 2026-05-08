"""Tests for meal_planner/scripts/export_sheet_to_db.py.

All tests use synthetic data — no gspread, no real DB, no live Gemini.
"""
from __future__ import annotations

from meal_planner.scripts.export_sheet_to_db import compute_diff


# Helpers

def _db(title: str, recipe_id: int = 1, ing_count: int = 3) -> tuple[str, tuple[int, str, int]]:
    return (title.lower(), (recipe_id, title, ing_count))


# ---------------------------------------------------------------------------
# compute_diff — basic cases
# ---------------------------------------------------------------------------

def test_no_diff() -> None:
    sheet = [("Mains", "Beef Stew", ["beef", "potato", "carrot"])]
    db = dict([_db("Beef Stew", 1, 3)])
    result = compute_diff(sheet, db)
    assert result["only_in_sheet"] == []
    assert result["only_in_db"] == []
    assert result["mismatch"] == []


def test_only_in_sheet() -> None:
    sheet = [("Mains", "Chicken Soup", ["chicken", "noodle"])]
    result = compute_diff(sheet, {})
    assert len(result["only_in_sheet"]) == 1
    tab, title, ings = result["only_in_sheet"][0]
    assert tab == "Mains"
    assert title == "Chicken Soup"
    assert ings == ["chicken", "noodle"]
    assert result["only_in_db"] == []
    assert result["mismatch"] == []


def test_only_in_db() -> None:
    db = dict([_db("Photo Recipe", 42, 5)])
    result = compute_diff([], db)
    assert result["only_in_sheet"] == []
    assert len(result["only_in_db"]) == 1
    rid, title = result["only_in_db"][0]
    assert rid == 42
    assert title == "Photo Recipe"
    assert result["mismatch"] == []


def test_ingredient_count_mismatch() -> None:
    sheet = [("Mains", "Beef Stew", ["beef", "potato"])]  # 2 ingredients
    db = dict([_db("Beef Stew", 1, 5)])  # DB has 5
    result = compute_diff(sheet, db)
    assert result["only_in_sheet"] == []
    assert result["only_in_db"] == []
    assert len(result["mismatch"]) == 1
    tab, title, s_count, db_count = result["mismatch"][0]
    assert title == "Beef Stew"
    assert s_count == 2
    assert db_count == 5


def test_case_insensitive_match() -> None:
    sheet = [("Soups", "beef stew", ["beef", "potato", "carrot"])]
    db = dict([_db("Beef Stew", 1, 3)])  # DB title is title-cased
    result = compute_diff(sheet, db)
    assert result["only_in_sheet"] == []
    assert result["only_in_db"] == []
    assert result["mismatch"] == []


def test_mixed_operations() -> None:
    sheet = [
        ("Mains", "Beef Stew", ["beef", "potato", "carrot"]),   # matches DB
        ("Soups", "Chicken Soup", ["chicken", "noodle"]),        # only in Sheet
        ("Soups", "Lentil Soup", ["lentil"]),                    # mismatch (DB has 3)
    ]
    db = {
        "beef stew": (1, "Beef Stew", 3),
        "lentil soup": (2, "Lentil Soup", 3),
        "photo pasta": (3, "Photo Pasta", 6),                    # only in DB
    }
    result = compute_diff(sheet, db)

    only_sheet_titles = [t for _, t, _ in result["only_in_sheet"]]
    assert only_sheet_titles == ["Chicken Soup"]

    only_db_titles = {t for _, t in result["only_in_db"]}
    assert only_db_titles == {"Photo Pasta"}

    assert len(result["mismatch"]) == 1
    _, title, s_count, db_count = result["mismatch"][0]
    assert title == "Lentil Soup"
    assert s_count == 1
    assert db_count == 3


def test_empty_sheet_and_db() -> None:
    result = compute_diff([], {})
    assert result == {"only_in_sheet": [], "only_in_db": [], "mismatch": []}


def test_whitespace_title_skipped() -> None:
    sheet = [("Mains", "   ", [])]  # blank title should be ignored
    result = compute_diff(sheet, {})
    assert result["only_in_sheet"] == []
