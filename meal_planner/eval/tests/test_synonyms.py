"""Tests for synonyms.yml and _normalize_ingredient_name()."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

SYNONYMS_PATH = Path(__file__).parent.parent / "synonyms.yml"

# Add eval/ to sys.path so we can import bake_off
sys.path.insert(0, str(Path(__file__).parent.parent))
from bake_off import _normalize_ingredient_name, _tokenize_ingredient_name  # noqa: E402


def test_synonyms_loads():
    data = yaml.safe_load(SYNONYMS_PATH.read_text(encoding="utf-8"))
    groups = data.get("synonyms", [])
    scallion_group = next(g for g in groups if g.startswith("scallion"))
    assert "green onion" in scallion_group


def test_unicode_fractions_loaded():
    data = yaml.safe_load(SYNONYMS_PATH.read_text(encoding="utf-8"))
    fractions = data.get("unicode_fractions", {})
    assert fractions["¼"] == 0.25


def test_normalize_synonym():
    assert _normalize_ingredient_name("green onion") == "scallion"
    assert _normalize_ingredient_name("courgette") == "zucchini"
    # Unknown ingredient passes through unchanged
    assert _normalize_ingredient_name("truffle") == "truffle"


def test_per_token_synonym():
    """'low-sodium soy sauce' tokenizes to canonical soy sauce tokens via full-name lookup."""
    data = yaml.safe_load(SYNONYMS_PATH.read_text(encoding="utf-8"))
    tokens = _tokenize_ingredient_name("low-sodium soy sauce", data)
    # Full-name lookup maps "low sodium soy sauce" → "soy sauce" → tokens {"soy", "sauce"}
    assert "soy" in tokens
    assert "sauce" in tokens
    # The "low" and "sodium" qualifiers should have been replaced by the canonical form
    assert "low" not in tokens
    assert "sodium" not in tokens


def test_garlic_clove_normalizes_to_garlic():
    """'garlic clove' tokenizes to {'garlic'} via full-name synonym lookup."""
    data = yaml.safe_load(SYNONYMS_PATH.read_text(encoding="utf-8"))
    tokens = _tokenize_ingredient_name("garlic clove", data)
    assert tokens == {"garlic"}
