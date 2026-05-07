"""Tests for meal_planner.vision._normalize — TDD for Option B normalizer."""
from __future__ import annotations

import pytest

from meal_planner.vision._normalize import normalize_extraction, normalize_ingredient


# ---------------------------------------------------------------------------
# Pattern 1: qty/unit fused (qty contains "number unit", unit is null/empty)
# ---------------------------------------------------------------------------

def test_p1_bare_digit():
    ing = {"qty": "1 teaspoon", "unit": None, "name": "olive oil"}
    out, warns = normalize_ingredient(ing)
    assert out["qty"] == "1"
    assert out["unit"] == "teaspoon"
    assert out["name"] == "olive oil"
    assert len(warns) == 1


def test_p1_fraction():
    ing = {"qty": "1/2 pound", "unit": None, "name": "orzo"}
    out, warns = normalize_ingredient(ing)
    assert out["qty"] == "1/2"
    assert out["unit"] == "pound"
    assert len(warns) == 1


def test_p1_mixed():
    ing = {"qty": "1 1/2 cups", "unit": None, "name": "sugar"}
    out, warns = normalize_ingredient(ing)
    assert out["qty"] == "1 1/2"
    assert out["unit"] == "cups"
    assert len(warns) == 1


def test_p1_range():
    ing = {"qty": "5-6 cloves", "unit": None, "name": "garlic"}
    out, warns = normalize_ingredient(ing)
    assert out["qty"] == "5-6"
    assert out["unit"] == "cloves"
    assert len(warns) == 1


def test_p1_decimal():
    ing = {"qty": "2.5 oz", "unit": None, "name": "butter"}
    out, warns = normalize_ingredient(ing)
    assert out["qty"] == "2.5"
    assert out["unit"] == "oz"
    assert len(warns) == 1


# ---------------------------------------------------------------------------
# Pattern 2: unit-in-name (name starts with a unit token)
# ---------------------------------------------------------------------------

def test_p2_singular():
    ing = {"qty": "1", "unit": None, "name": "teaspoon turmeric"}
    out, warns = normalize_ingredient(ing)
    assert out["unit"] == "teaspoon"
    assert out["name"] == "turmeric"
    assert len(warns) == 1


def test_p2_plural():
    ing = {"qty": "5-6", "unit": None, "name": "cloves Garlic"}
    out, warns = normalize_ingredient(ing)
    assert out["unit"] == "cloves"
    assert out["name"] == "Garlic"
    assert len(warns) == 1


def test_p2_capitalized():
    ing = {"qty": "1", "unit": None, "name": "Teaspoon Turmeric"}
    out, warns = normalize_ingredient(ing)
    assert out["unit"] == "Teaspoon"
    assert out["name"] == "Turmeric"
    assert len(warns) == 1


def test_p2_abbreviated():
    ing = {"qty": "2", "unit": None, "name": "tsp salt"}
    out, warns = normalize_ingredient(ing)
    assert out["unit"] == "tsp"
    assert out["name"] == "salt"
    assert len(warns) == 1


# ---------------------------------------------------------------------------
# No-op cases
# ---------------------------------------------------------------------------

def test_noop_unit_already_set():
    ing = {"qty": "1", "unit": "cup", "name": "flour"}
    out, warns = normalize_ingredient(ing)
    assert out == ing
    assert warns == []


def test_noop_qty_null():
    ing = {"qty": None, "unit": None, "name": "salt to taste"}
    out, warns = normalize_ingredient(ing)
    assert out == ing
    assert warns == []


def test_noop_name_has_no_unit():
    """'large' is intentionally NOT in the unit vocab."""
    ing = {"qty": "1", "unit": None, "name": "large eggs"}
    out, warns = normalize_ingredient(ing)
    assert out == ing
    assert warns == []


def test_noop_single_word_name():
    ing = {"qty": "1", "unit": None, "name": "egg"}
    out, warns = normalize_ingredient(ing)
    assert out == ing
    assert warns == []


# ---------------------------------------------------------------------------
# Edge-case behavior
# ---------------------------------------------------------------------------

def test_no_double_fire_p1_then_p2():
    """Pattern 1 fires → name is not re-checked for Pattern 2."""
    ing = {"qty": "1 teaspoon", "unit": None, "name": "olive oil"}
    out, warns = normalize_ingredient(ing)
    assert out["qty"] == "1"
    assert out["unit"] == "teaspoon"
    assert out["name"] == "olive oil"
    assert len(warns) == 1, f"Expected 1 warning, got {warns}"


def test_p2_stops_at_first_unit_token():
    """Only the first token moves to unit; rest of name stays intact."""
    ing = {"qty": "1", "unit": None, "name": "cup of cup-sized portions"}
    out, warns = normalize_ingredient(ing)
    assert out["unit"] == "cup"
    assert out["name"] == "of cup-sized portions"
    assert len(warns) == 1


# ---------------------------------------------------------------------------
# Pattern 3: qty/unit fused + unit field has non-unit garbage
# ---------------------------------------------------------------------------

def test_p3_fused_with_ingredient_in_unit():
    """qty='2 tsp', unit='vegetable oil' — unit is not a real measurement."""
    ing = {"qty": "2 tsp", "unit": "vegetable oil", "name": "vegetable oil"}
    out, warns = normalize_ingredient(ing)
    assert out["qty"] == "2"
    assert out["unit"] == "tsp"
    assert out["name"] == "vegetable oil"
    assert len(warns) == 1


def test_p3_fraction_with_prep_in_unit():
    """qty='1/2 cup', unit='sour cream' — unit is ingredient text."""
    ing = {"qty": "1/2 cup", "unit": "sour cream", "name": "sour cream"}
    out, warns = normalize_ingredient(ing)
    assert out["qty"] == "1/2"
    assert out["unit"] == "cup"
    assert out["name"] == "sour cream"
    assert len(warns) == 1


def test_p3_noop_when_unit_is_real():
    """qty='2 cups', unit='cup' — unit is already a real unit, no change."""
    ing = {"qty": "2 cups", "unit": "cup", "name": "flour"}
    out, warns = normalize_ingredient(ing)
    assert out == ing
    assert warns == []


# ---------------------------------------------------------------------------
# normalize_extraction over a full dict
# ---------------------------------------------------------------------------

_ORZO_SIDECAR = {
    "title": "Easy Sausage and Pea Orzo Risotto",
    "ingredients": [
        {"qty": "1 teaspoon", "unit": None, "name": "olive oil"},
        {"qty": "10 ounce", "unit": None, "name": "Italian sausage, removed from its casing"},
        {"qty": "1/4 cup", "unit": None, "name": "minced shallot"},
        {"qty": "1/2 pound", "unit": None, "name": "orzo"},
        {"qty": "3 cup", "unit": None, "name": "hot water or low-sodium vegetable or chicken stock"},
        {"qty": None, "unit": None, "name": "kosher salt"},
        {"qty": None, "unit": None, "name": "freshly ground black pepper"},
        {"qty": "1 cup", "unit": None, "name": "frozen peas"},
        {"qty": "1/4 cup", "unit": None, "name": "finely grated Parmigiano-Reggiano"},
        {"qty": None, "unit": None, "name": "chopped flat-leaf parsley (optional)"},
    ],
    "tags": ["italian", "pasta", "weeknight"],
}


def test_normalize_extraction_orzo():
    """7 fused ingredients normalized; 3 empty-qty pass through. 7 warnings."""
    result, warns = normalize_extraction(_ORZO_SIDECAR)
    assert len(warns) == 7, f"Expected 7 warnings, got {len(warns)}: {warns}"
    # All 7 non-null qty ingredients should now have a unit set
    ings = result["ingredients"]
    for ing in ings:
        if ing["qty"] not in (None, ""):
            assert ing["unit"] not in (None, ""), f"Unit missing after normalize: {ing}"
    # Title and tags pass through
    assert result["title"] == _ORZO_SIDECAR["title"]
    assert result["tags"] == _ORZO_SIDECAR["tags"]
    # Input not mutated
    assert _ORZO_SIDECAR["ingredients"][0]["unit"] is None
