"""
Grocery list consolidation via Gemini-2.5-flash-lite.

consolidate_for_grocery() scales each recipe's ingredients to the requested
serving count, then sends the full combined list to Gemini for fuzzy
consolidation + section categorisation in a single call.  The model choice
(flash-lite) is intentional for V0 to match seed_from_sheet.py; Phase 15's
bake-off will revisit — switching is a one-line change here.
"""
from __future__ import annotations

import json
import re
import sys
from typing import TYPE_CHECKING

import requests

from meal_planner.models import GroceryLine
from meal_planner.scaling import scale_ingredients

if TYPE_CHECKING:
    from pathlib import Path

    from meal_planner.models import Recipe

_GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash-lite:generateContent"
)

_PROMPT_TEMPLATE = """\
You are a grocery list assistant. Consolidate this ingredient list:
- Combine duplicate or equivalent ingredients into one entry
- Sum quantities where possible (e.g. '1 cup olive oil' + '2 tbsp olive oil' → '1 cup + 2 tbsp olive oil')
- Assign each item to one of these sections: {section_names}
- Keep the ingredient name clean (no quantity or unit in the name field)

Ingredients:
{ingredient_lines}

Respond with a JSON array only — no other text:
[{{"name": "olive oil", "qty": 1.5, "unit": "cup", "section": "Pantry"}}, ...]

Rules:
- qty: numeric total quantity; null if uncountable or amount is vague (e.g. "to taste", "a pinch")
- unit: unit string, "" if none
- name: ingredient name only
- section: one of the provided section names; use "{fallback}" if unsure

Use the exact section names provided."""


def _call_gemini(prompt: str, api_key: str) -> str | None:
    """Call Gemini with 429/503 retry. Returns response text or None on failure."""
    resp = None
    for attempt in range(4):
        resp = requests.post(
            _GEMINI_ENDPOINT,
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=60,
        )
        if resp.status_code not in (429, 503):
            break
        body = resp.json()
        retry_delay = 60
        for detail in body.get("error", {}).get("details", []):
            if detail.get("@type", "").endswith("RetryInfo"):
                delay_str = detail.get("retryDelay", "60s")
                retry_delay = int(re.sub(r"[^0-9]", "", delay_str) or "60") + 2
                break
        import time
        print(f"consolidation: rate limited — waiting {retry_delay}s…", flush=True)
        time.sleep(retry_delay)

    if resp is None or resp.status_code != 200:
        print(
            f"consolidation: Gemini HTTP {resp.status_code if resp else '?'}: "
            f"{resp.text[:200] if resp else ''}",
            file=sys.stderr,
        )
        return None

    try:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        print(f"consolidation: unexpected Gemini response shape: {exc}", file=sys.stderr)
        return None


def consolidate_for_grocery(
    items: list[tuple["Recipe", int]],
    *,
    sections: list[str],
    api_key: str,
    path: "Path | None" = None,
) -> list[GroceryLine]:
    """Consolidate and section-categorise ingredients for a grocery send.

    Scales each recipe to the requested serving count, concatenates all
    ingredient lines, sends to Gemini for fuzzy consolidation + sectioning,
    and returns GroceryLine[].

    source_recipe_titles is left empty for V0 (Gemini consolidates across
    recipes, so 1:1 attribution is lost); Phase 18 can add it if needed.

    Unparseable Gemini response → returns []; never raises.
    """
    if not items:
        return []

    fallback = sections[0] if sections else ""
    ingredient_lines: list[str] = []

    for recipe, target_servings in items:
        scaled = scale_ingredients(recipe, target_servings, path=path)
        for ing in scaled:
            qty = ing.qty_per_serving  # already scaled by scale_ingredients
            if qty is not None:
                line = f"{qty:.4g} {ing.unit or ''} {ing.name}".strip()
            else:
                line = ing.name
            if ing.notes:
                line += f" ({ing.notes})"
            ingredient_lines.append(line)

    if not ingredient_lines:
        return []

    section_names = ", ".join(sections) if sections else "Other"
    prompt = _PROMPT_TEMPLATE.format(
        section_names=section_names,
        fallback=fallback,
        ingredient_lines="\n".join(f"- {l}" for l in ingredient_lines),
    )

    text = _call_gemini(prompt, api_key)
    if text is None:
        return []

    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        print(
            "consolidation: could not find JSON array in Gemini response",
            file=sys.stderr,
        )
        return []

    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        print(f"consolidation: JSON parse error: {exc}", file=sys.stderr)
        return []

    if not isinstance(raw, list):
        print("consolidation: Gemini response is not a list", file=sys.stderr)
        return []

    if len(raw) < len(ingredient_lines) * 0.5:
        print(
            f"consolidation: WARN — Gemini returned {len(raw)} items from "
            f"{len(ingredient_lines)} input lines; some may have been silently dropped",
            file=sys.stderr,
        )

    result: list[GroceryLine] = []
    unknown_sections: list[str] = []

    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue

        qty_raw = item.get("qty")
        try:
            qty: float | None = float(qty_raw) if qty_raw is not None else None
        except (TypeError, ValueError):
            qty = None

        unit = str(item.get("unit", "") or "").strip()
        section_raw = str(item.get("section", "") or "").strip()

        if section_raw and section_raw not in sections:
            unknown_sections.append(section_raw)
            section_raw = fallback
        elif not section_raw:
            section_raw = fallback

        result.append(GroceryLine(
            name=name,
            qty=qty,
            unit=unit,
            source_recipe_titles=[],
            todoist_section=section_raw,
        ))

    if unknown_sections:
        print(
            f"consolidation: WARN — unknown section name(s) from Gemini, "
            f"fell back to {fallback!r}: {sorted(set(unknown_sections))}",
            file=sys.stderr,
        )

    return result
