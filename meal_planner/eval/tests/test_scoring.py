"""Tests for scoring rubric: _score, _normalize_qty, _normalize_unit, _normalize_ingredient_name."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from bake_off import (  # noqa: E402
    _casefold_strip_punct,
    _normalize_ingredient_name,
    _normalize_qty,
    _normalize_unit,
    _qty_matches,
    _score,
)

_SYNONYMS_PATH = Path(__file__).parent.parent / "synonyms.yml"


def _load_synonyms():
    return yaml.safe_load(_SYNONYMS_PATH.read_text(encoding="utf-8"))


def _fractions():
    return _load_synonyms()["unicode_fractions"]


def _synonyms():
    return _load_synonyms()


# ---------------------------------------------------------------------------
# PHASE15 required tests (8)
# ---------------------------------------------------------------------------

def test_perfect_match():
    synonyms = _synonyms()
    fractions = _fractions()
    extracted = {
        "title": "Spaghetti Bolognese",
        "ingredients": [
            {"qty": "2", "unit": "tbsp", "name": "olive oil"},
            {"qty": "1", "unit": "lb", "name": "ground beef"},
        ],
        "tags": ["italian"],
    }
    golden = {
        "title": "Spaghetti Bolognese",
        "ingredients": [
            {"qty": "2", "unit": "tbsp", "name": "olive oil"},
            {"qty": "1", "unit": "lb", "name": "ground beef"},
        ],
        "tags": ["italian"],
    }
    result = _score(extracted, golden, synonyms, fractions)
    assert result["structural_validity"] is True
    assert result["ingredient_f1"] == 1.0
    assert result["parse_correctness"] == 1.0
    assert result["title_accuracy"] == 1.0


def test_synonym_match():
    """Model uses 'green onion'; golden uses 'scallion' — should score as full match."""
    synonyms = _synonyms()
    fractions = _fractions()
    extracted = {
        "title": "Stir Fry",
        "ingredients": [{"qty": "2", "unit": "tbsp", "name": "green onion"}],
        "tags": [],
    }
    golden = {
        "title": "Stir Fry",
        "ingredients": [{"qty": "2", "unit": "tbsp", "name": "scallion"}],
        "tags": [],
    }
    result = _score(extracted, golden, synonyms, fractions)
    assert result["ingredient_f1"] == 1.0


def test_unicode_fraction_match():
    """Extracted qty '¼' should match golden qty '0.25'."""
    fractions = _fractions()
    assert _qty_matches("¼", "0.25", fractions)


def test_range_matches_scalar():
    """Extracted qty '2-3' should match golden qty '2'."""
    fractions = _fractions()
    assert _qty_matches("2-3", "2", fractions)
    assert _qty_matches("2", "2-3", fractions)


def test_to_taste_normalizes_to_null():
    """Extracted qty 'to taste' normalizes same as golden qty None."""
    fractions = _fractions()
    assert _normalize_qty("to taste", fractions) is None
    assert _qty_matches("to taste", None, fractions)


def test_ingredients_string_not_list_fails_structural():
    """If ingredients is a string instead of a list, structural_validity is False."""
    synonyms = _synonyms()
    fractions = _fractions()
    extracted = {
        "title": "Omelette",
        "ingredients": "1 cup oil",
        "tags": [],
    }
    golden = {
        "title": "Omelette",
        "ingredients": [{"qty": "1", "unit": "cup", "name": "oil"}],
        "tags": [],
    }
    result = _score(extracted, golden, synonyms, fractions)
    assert result["structural_validity"] is False
    assert result["ingredient_f1"] == 0.0
    assert "ingredients_not_list" in result["errors"]


def test_ingredient_f1_partial_match():
    """5 extracted, 5 golden, 3 overlap → F1 = 0.6."""
    synonyms = _synonyms()
    fractions = _fractions()

    def _make_ing(names):
        return [{"qty": None, "unit": None, "name": n} for n in names]

    extracted = {
        "title": "Dish",
        "ingredients": _make_ing(["a", "b", "c", "d", "e"]),
        "tags": [],
    }
    golden = {
        "title": "Dish",
        "ingredients": _make_ing(["a", "b", "c", "x", "y"]),
        "tags": [],
    }
    result = _score(extracted, golden, synonyms, fractions)
    assert abs(result["ingredient_f1"] - 0.6) < 1e-9


def test_title_casefold():
    """Extracted 'ONE-PAN ORZO!' should match golden 'One-Pan Orzo'."""
    assert _casefold_strip_punct("ONE-PAN ORZO!") == _casefold_strip_punct("One-Pan Orzo")
    synonyms = _synonyms()
    fractions = _fractions()
    extracted = {
        "title": "ONE-PAN ORZO!",
        "ingredients": [],
        "tags": [],
    }
    golden = {
        "title": "One-Pan Orzo",
        "ingredients": [],
        "tags": [],
    }
    result = _score(extracted, golden, synonyms, fractions)
    assert result["title_accuracy"] == 1.0


# ---------------------------------------------------------------------------
# HUMAN-1 amendment tests
# ---------------------------------------------------------------------------

def test_mixed_number_qty():
    """'1 1/2' and '6 1/2' (mixed numbers) must normalize and match their decimal forms."""
    fractions = _fractions()
    assert _normalize_qty("1 1/2", fractions) == "1.5"
    assert _normalize_qty("6 1/2", fractions) == "6.5"
    assert _qty_matches("1 1/2", "1.5", fractions)
    assert _qty_matches("6 1/2", "6.5", fractions)


def test_fraction_range_qty():
    """'1/3-1/2' range: scalar '1/3' should match, '1' should not."""
    fractions = _fractions()
    # Scalar within range matches
    assert _qty_matches("1/3", "1/3-1/2", fractions)
    assert _qty_matches("1/3-1/2", "1/3", fractions)
    # Scalar outside range does not match
    assert not _qty_matches("1", "1/3-1/2", fractions)


def test_title_casefold_apostrophe():
    """'Mom's Dan Gung' must match 'moms dan gung' after stripping apostrophes."""
    assert _casefold_strip_punct("Mom's Dan Gung") == _casefold_strip_punct("moms dan gung")
    synonyms = _synonyms()
    fractions = _fractions()
    extracted = {
        "title": "Mom's Dan Gung",
        "ingredients": [],
        "tags": [],
    }
    golden = {
        "title": "moms dan gung",
        "ingredients": [],
        "tags": [],
    }
    result = _score(extracted, golden, synonyms, fractions)
    assert result["title_accuracy"] == 1.0
