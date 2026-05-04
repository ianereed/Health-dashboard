"""Plan tab — Recipes view with Send-to-Todoist (Phase 14.5).

Renders a recipe browser with a scale slider and a "Send to Todoist" button
that enqueues the meal_planner_send_to_todoist Job kind.
Tab label stays "Plan" until Phase 14.6 renames it to "Recipes".
"""
from __future__ import annotations

import streamlit as st

from meal_planner import db as _db
from meal_planner import queries, scaling


def render() -> None:
    try:
        _render_inner()
    except Exception as exc:
        st.error("Plan tab error — see traceback below")
        st.exception(exc)


def _render_inner() -> None:
    if not _db.DB_PATH.exists():
        st.info(
            "**No recipes seeded yet.**\n\n"
            "Run `python -m meal_planner.seed_from_sheet` on the mini to populate "
            "the recipe database, then refresh."
        )
        return

    recipes = queries.list_recipes()
    if not recipes:
        st.info("Recipe database exists but contains no recipes yet.")
        return

    recipe_map = {r.title: r for r in recipes}
    chosen_title = st.selectbox("Recipe", list(recipe_map.keys()))
    recipe = recipe_map[chosen_title]

    col_slider, col_btn = st.columns([3, 1])
    with col_slider:
        target = st.slider(
            "Servings",
            min_value=1,
            max_value=20,
            value=recipe.base_servings,
        )
    with col_btn:
        st.write("")  # vertical alignment spacer
        send_clicked = st.button("Send to Todoist", type="primary")

    st.caption(f"Base: {recipe.base_servings} servings → scaling to {target}")

    if send_clicked:
        try:
            from jobs.kinds.meal_planner_send_to_todoist import meal_planner_send_to_todoist
            result = meal_planner_send_to_todoist([[recipe.id, target]])
            st.success(f"Job enqueued — task ID: {getattr(result, 'id', '?')}")
        except Exception as exc:
            st.error(f"Failed to enqueue: {exc}")

    ingredients = scaling.scale_ingredients(recipe, target)
    if not ingredients:
        st.write("No ingredients recorded for this recipe.")
        return

    rows = []
    for ing in ingredients:
        qty_str = f"{ing.qty_per_serving:.2g}" if ing.qty_per_serving is not None else "—"
        unit_str = ing.unit or ""
        rows.append({"Ingredient": ing.name, "Qty": qty_str, "Unit": unit_str})

    st.table(rows)
