"""Post-extraction normalizer for LLM qty/unit output bugs.

Fixes two deterministic failure modes without touching the prompt:
  1. qty/unit fused — qty='1 teaspoon', unit=null  →  qty='1', unit='teaspoon'
  2. unit-in-name  — qty='1', unit=null, name='teaspoon turmeric'
                  →  qty='1', unit='teaspoon', name='turmeric'

Pure functions; no mutation of inputs.
"""
from __future__ import annotations

import re

_UNIT_VOCAB = frozenset({
    # volume
    "tsp", "tsp.", "teaspoon", "teaspoons",
    "tbsp", "tbsp.", "tablespoon", "tablespoons",
    "cup", "cups", "c", "c.",
    "ml", "milliliter", "milliliters",
    "l", "liter", "liters", "litre", "litres",
    "fl", "floz",
    "pint", "pints", "pt",
    "quart", "quarts", "qt",
    "gallon", "gallons", "gal",
    # mass
    "oz", "oz.", "ounce", "ounces",
    "lb", "lb.", "lbs", "lbs.", "pound", "pounds",
    "g", "gram", "grams",
    "kg", "kilogram", "kilograms",
    # count-ish
    "clove", "cloves",
    "head", "heads",
    "stick", "sticks",
    "can", "cans",
    "package", "packages", "pkg", "pkgs",
    "sprig", "sprigs",
    "bunch", "bunches",
    "slice", "slices",
    "piece", "pieces",
    "fillet", "fillets",
    "sheet", "sheets",
    "pack", "packs",
    # vague-amount tokens
    "pinch", "pinches",
    "dash", "dashes",
})

# Matches: <number> <word>   (anchored to full string)
# Number alternatives ordered longest-first to avoid partial matches:
#   mixed fraction  1 1/2
#   fraction        1/2
#   range           5-6  or  1.5-2
#   decimal/int     2.5  or  1
_FUSED_RE = re.compile(
    r"^(\d+\s+\d+/\d+|\d+/\d+|\d+\.?\d*-\d+\.?\d*|\d+\.?\d*)\s+(\S+)$"
)


def _is_unit_token(tok: str) -> bool:
    """Case-insensitive membership check against _UNIT_VOCAB."""
    return tok.lower() in _UNIT_VOCAB


def normalize_ingredient(ing: dict) -> tuple[dict, list[str]]:
    """Return (normalized_dict, warnings_list).

    Patterns applied in order — first match short-circuits the rest:
      1. qty/unit fused, unit empty: qty='1 teaspoon', unit=null/''
         → qty='1', unit='teaspoon'
      2. unit-in-name, unit empty: qty='1', unit=null, name='teaspoon turmeric'
         → qty='1', unit='teaspoon', name='turmeric'
      3. qty/unit fused, unit is non-unit text: qty='2 tsp', unit='vegetable oil'
         → qty='2', unit='tsp', name unchanged (old unit discarded; name is canonical)

    Does NOT mutate input.
    """
    qty = ing.get("qty")
    unit = ing.get("unit")
    name = ing.get("name", "") or ""
    warnings: list[str] = []

    if qty is None or (isinstance(qty, str) and qty.strip() == ""):
        return ing, warnings

    qty_s = str(qty).strip()
    unit_s = str(unit).strip() if unit is not None else ""

    unit_missing = not unit_s

    if unit_missing:
        # Pattern 1: qty/unit fused
        m = _FUSED_RE.match(qty_s)
        if m:
            num_part = m.group(1)
            unit_candidate = m.group(2)
            if _is_unit_token(unit_candidate):
                warnings.append(
                    f"normalize: qty='{qty_s}' split → qty='{num_part}' unit='{unit_candidate}'"
                )
                return {**ing, "qty": num_part, "unit": unit_candidate}, warnings

        # Pattern 2: unit-in-name
        tokens = name.split(None, 1)
        if tokens and _is_unit_token(tokens[0]):
            actual_unit = tokens[0]
            new_name = tokens[1] if len(tokens) > 1 else ""
            warnings.append(
                f"normalize: name='{name}' split → unit='{actual_unit}' name='{new_name}'"
            )
            return {**ing, "unit": actual_unit, "name": new_name}, warnings
    else:
        # Pattern 3: qty fused + unit has non-unit garbage (ingredient text / prep note)
        # Only applies when the current unit value is not a real cooking measurement.
        if not _is_unit_token(unit_s):
            m = _FUSED_RE.match(qty_s)
            if m:
                num_part = m.group(1)
                unit_candidate = m.group(2)
                if _is_unit_token(unit_candidate):
                    warnings.append(
                        f"normalize: qty='{qty_s}' unit='{unit_s}' fused+nonunit → "
                        f"qty='{num_part}' unit='{unit_candidate}'"
                    )
                    return {**ing, "qty": num_part, "unit": unit_candidate}, warnings

    return ing, warnings


def normalize_extraction(parsed: dict) -> tuple[dict, list[str]]:
    """Apply normalize_ingredient to every entry in parsed['ingredients'].

    Returns (new_parsed, all_warnings). Passes title and tags through unchanged.
    If 'ingredients' is missing or not a list, returns (parsed, []) unchanged.
    """
    ings = parsed.get("ingredients")
    if not isinstance(ings, list):
        return parsed, []

    all_warnings: list[str] = []
    normalized: list[dict] = []
    for i, ing in enumerate(ings):
        norm_ing, w = normalize_ingredient(ing)
        normalized.append(norm_ing)
        for warning in w:
            all_warnings.append(f"row {i}: {warning}")

    return {**parsed, "ingredients": normalized}, all_warnings
