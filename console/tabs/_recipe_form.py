"""Pure-function helpers for the recipe edit form.

No ``import streamlit`` at the top level — all helpers are unit-testable
without a running Streamlit server. Streamlit imports belong in plan.py.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_recipe_form(payload: dict) -> tuple[bool, list[str]]:
    """Validate a recipe form payload.

    Expected keys (all optional except 'title'):
      title: str
      base_servings: int | float
      instructions: str
      cook_time_min: int | float | None
      source: str

    Returns (ok, errs). When ok is True, errs is empty.
    """
    errs: list[str] = []
    title = payload.get("title", "")
    if not isinstance(title, str) or not title.strip():
        errs.append("Title is required.")

    base_servings = payload.get("base_servings")
    if base_servings is not None:
        try:
            v = int(base_servings)
            if v < 1:
                errs.append("Servings must be at least 1.")
        except (TypeError, ValueError):
            errs.append("Servings must be a whole number.")

    cook_time_min = payload.get("cook_time_min")
    if cook_time_min is not None and cook_time_min != "":
        try:
            v = int(cook_time_min)
            if v < 0:
                errs.append("Cook time cannot be negative.")
        except (TypeError, ValueError):
            errs.append("Cook time must be a whole number of minutes.")

    return (len(errs) == 0, errs)


# ---------------------------------------------------------------------------
# Ingredient diff
# ---------------------------------------------------------------------------

def diff_ingredients(
    before: list[dict], after: list[dict]
) -> dict[str, list[dict]]:
    """Compute adds/updates/deletes between two ingredient lists.

    Each dict must have an ``id`` key (int) for existing rows.
    New rows from the editor have id == 0 or id == None (data_editor appends
    with no id).

    Returns::

        {
            "adds":    [row, ...],      # rows with no existing id
            "updates": [row, ...],      # rows whose id exists in before
            "deletes": [row, ...],      # before rows whose id is absent from after
        }

    Only rows that actually changed are included in "updates" — comparison
    excludes the ``id`` field itself.
    """
    before_by_id = {row["id"]: row for row in before if row.get("id")}

    after_ids: set[int] = set()
    adds: list[dict] = []
    updates: list[dict] = []

    for row in after:
        rid = row.get("id")
        if not rid:
            adds.append(row)
        else:
            after_ids.add(rid)
            old = before_by_id.get(rid)
            if old is None:
                # id present in after but not before — treat as add
                adds.append({k: v for k, v in row.items() if k != "id"})
            else:
                old_cmp = {k: v for k, v in old.items() if k != "id"}
                new_cmp = {k: v for k, v in row.items() if k != "id"}
                if old_cmp != new_cmp:
                    updates.append(row)

    deletes = [row for row in before if row.get("id") and row["id"] not in after_ids]

    return {"adds": adds, "updates": updates, "deletes": deletes}


# ---------------------------------------------------------------------------
# Tag normalization
# ---------------------------------------------------------------------------

def normalize_tags(raw_tags: list[str]) -> list[str]:
    """Lowercase, strip whitespace, and deduplicate. Preserves first-seen order."""
    seen: dict[str, None] = {}
    for t in raw_tags:
        t = t.strip().lower()
        if t:
            seen[t] = None
    return list(seen)


# ---------------------------------------------------------------------------
# Ingredient list → editor rows
# ---------------------------------------------------------------------------

def ingredients_to_rows(ingredients: list) -> list[dict]:
    """Convert Ingredient dataclass instances to plain dicts for st.data_editor.

    The ``id`` field is kept so diff_ingredients can match rows on save.
    """
    return [
        {
            "id": ing.id,
            "name": ing.name,
            "qty_per_serving": ing.qty_per_serving,
            "unit": ing.unit or "",
            "notes": ing.notes or "",
            "todoist_section": ing.todoist_section or "",
            "sort_order": ing.sort_order,
        }
        for ing in ingredients
    ]
