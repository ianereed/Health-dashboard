"""Tests for meal_planner.qty_parse.parse_qty."""
from __future__ import annotations

import pytest

from meal_planner.qty_parse import parse_qty


@pytest.mark.parametrize("s,expected", [
    # --- numeric path ---
    ("1",           (1.0,   "1")),
    ("2.5",         (2.5,   "2.5")),
    ("1.0",         (1.0,   "1.0")),
    ("0",           (0.0,   "0")),
    ("1/4",         (0.25,  "1/4")),
    ("3/8",         (0.375, "3/8")),
    ("0/5",         (0.0,   "0/5")),          # zero numerator valid
    ("1 1/2",       (1.5,   "1 1/2")),        # mixed fraction
    ("  1 1/2 ",    (1.5,   "1 1/2")),        # whitespace tolerant
    ("1\t1/2",      (1.5,   "1 1/2")),        # tab separator
    ("½",           (0.5,   "1/2")),           # unicode fraction
    ("1½",          (1.5,   "1 1/2")),        # whole + unicode fraction (no space)
    ("1 ½",         (1.5,   "1 1/2")),        # whole + unicode fraction (space)
    ("1 / 2",       (0.5,   "1/2")),          # spaces around slash, normalized
    # --- non-numeric path ---
    ("1/4 cup plus 2 tablespoons", (None, "1/4 cup plus 2 tablespoons")),
    ("to taste",    (None, "to taste")),
    ("a pinch",     (None, "a pinch")),
    ("abc",         (None, "abc")),
    ("-1",          (None, "-1")),             # negatives refused
    ("1.5.5",       (None, "1.5.5")),
    ("1/0",         (None, "1/0")),            # ZeroDivisionError-safe
    ("0/0",         (None, "0/0")),
    ("",            (None, "")),
    (None,          (None, "")),
    ("  ",          (None, "")),
    ("1/2/3",       (None, "1/2/3")),          # multi-slash junk
    ("🍕",          (None, "🍕")),              # emoji
])
def test_parse_qty(s, expected):
    assert parse_qty(s) == expected
