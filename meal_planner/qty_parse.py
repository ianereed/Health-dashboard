"""Tolerant recipe quantity parser.

Public API: parse_qty(s) → (float | None, str)
"""
from __future__ import annotations

import re

# Unicode fraction characters → (numerator, denominator) as strings
_UNICODE_FRACS: dict[str, tuple[str, str]] = {
    "½": ("1", "2"), "⅓": ("1", "3"), "⅔": ("2", "3"),
    "¼": ("1", "4"), "¾": ("3", "4"), "⅕": ("1", "5"),
    "⅖": ("2", "5"), "⅗": ("3", "5"), "⅘": ("4", "5"),
    "⅙": ("1", "6"), "⅚": ("5", "6"), "⅛": ("1", "8"),
    "⅜": ("3", "8"), "⅝": ("5", "8"), "⅞": ("7", "8"),
}

_FRAC_RE = re.compile(r"^(\d+)\s*/\s*(\d+)$")
_WHOLE_RE = re.compile(r"^(\d+(?:\.\d+)?)$")
_MIXED_RE = re.compile(r"^(\d+)[\s\t]+(\d+)\s*/\s*(\d+)$")


def _expand_unicode(s: str) -> str:
    """Replace any Unicode fraction chars with their ASCII 'n/d' form."""
    for ch, (n, d) in _UNICODE_FRACS.items():
        s = s.replace(ch, f" {n}/{d}")
    return s


def parse_qty(s: str | None) -> tuple[float | None, str]:
    """Parse a recipe quantity string. Returns (numeric_or_None, normalized_raw).

    Numeric path:
        "1"          → (1.0,   "1")
        "2.5"        → (2.5,   "2.5")
        "1/4"        → (0.25,  "1/4")
        "3/8"        → (0.375, "3/8")
        "1 1/2"      → (1.5,   "1 1/2")     # mixed fraction
        "  1 1/2 "   → (1.5,   "1 1/2")     # whitespace tolerant
        "½"          → (0.5,   "1/2")        # unicode fractions
        "1½"         → (1.5,   "1 1/2")
        "1 ½"        → (1.5,   "1 1/2")
        "0"          → (0.0,   "0")
        "0/5"        → (0.0,   "0/5")        # zero numerator is valid
        "1 / 2"      → (0.5,   "1/2")        # spaces around slash accepted, normalized

    Non-numeric (verbatim preserved — pipeline keeps the row, qty_per_serving NULL):
        "1/4 cup plus 2 tablespoons" → (None, "1/4 cup plus 2 tablespoons")
        "to taste"                   → (None, "to taste")
        "a pinch"                    → (None, "a pinch")
        "abc"                        → (None, "abc")
        "-1"                         → (None, "-1")       # negatives refused
        "1.5.5"                      → (None, "1.5.5")
        "1/0"                        → (None, "1/0")      # ZeroDivisionError-safe
        "0/0"                        → (None, "0/0")
        ""                           → (None, "")
        None                         → (None, "")
        "  "                         → (None, "")
        "1/2/3"                      → (None, "1/2/3")    # multi-slash junk

    MUST NEVER raise. All ZeroDivisionError, ValueError, TypeError paths
    return (None, original-string-or-empty).
    """
    try:
        if s is None:
            return (None, "")
        raw = s.strip()
        if not raw:
            return (None, "")

        # Expand unicode fractions, trim again, collapse internal whitespace.
        expanded = _expand_unicode(raw).strip()

        # --- simple whole number or decimal ---
        m = _WHOLE_RE.match(expanded)
        if m:
            val = float(m.group(1))
            if val < 0:
                return (None, raw)
            return (val, expanded)

        # --- mixed fraction: "1 1/2" (or after unicode expansion: "1  1/2") ---
        m = _MIXED_RE.match(expanded)
        if m:
            whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if den == 0 or whole < 0 or num < 0:
                return (None, raw)
            val = whole + num / den
            normalized = f"{whole} {num}/{den}"
            return (val, normalized)

        # --- simple fraction: "1/4" (spaces around slash allowed) ---
        m = _FRAC_RE.match(expanded)
        if m:
            num, den = int(m.group(1)), int(m.group(2))
            if den == 0:
                return (None, raw)
            val = num / den
            normalized = f"{num}/{den}"
            return (val, normalized)

        # Anything else (compound, text, junk) — preserve original raw.
        return (None, raw)

    except Exception:
        return (None, s if s is not None else "")
