"""Recipes tab — recipe browser with Send-to-Todoist (Phase 14.6).

Renders a recipe browser with a scale slider and a "Send to Todoist" button
that enqueues the meal_planner_send_to_todoist Job kind.
Tab label stays "Plan" until Phase 14.6 renames it to "Recipes".
"""
from __future__ import annotations

import time

import streamlit as st

from meal_planner import db as _db
from meal_planner import queries, scaling

_CONFIRM_CLEAR_TTL = 10  # seconds before the confirm state resets


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

    st.divider()
    _render_clear_button()

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


def _render_clear_button() -> None:
    """Two-click confirm button that enqueues meal_planner_clear_todoist.

    First click sets a timestamp in session_state. Second click within
    _CONFIRM_CLEAR_TTL seconds fires the job. Expired state resets and
    the user must click again.
    """
    st.caption(
        "This deletes only items labeled `meal-planner`. "
        "Event-aggregator and finance-monitor tasks are untouched."
    )

    confirm_at = st.session_state.get("_confirm_clear_at")
    now = time.monotonic()

    if confirm_at is not None and now - confirm_at > _CONFIRM_CLEAR_TTL:
        # Expired — reset and treat as first click
        del st.session_state["_confirm_clear_at"]
        confirm_at = None

    if confirm_at is None:
        if st.button("Clear all meal-planner items from Todoist", type="secondary"):
            st.session_state["_confirm_clear_at"] = time.monotonic()
            st.rerun()
    else:
        remaining = int(_CONFIRM_CLEAR_TTL - (now - confirm_at))
        st.warning(f"Are you sure? Click again within {remaining}s to confirm.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, clear all meal-planner tasks", type="primary"):
                del st.session_state["_confirm_clear_at"]
                try:
                    from jobs.kinds.meal_planner_clear_todoist import meal_planner_clear_todoist
                    result = meal_planner_clear_todoist()
                    st.success(f"Job enqueued — task ID: {getattr(result, 'id', '?')}. Check Jobs tab for results.")
                except Exception as exc:
                    st.error(f"Failed to enqueue: {exc}")
        with col_no:
            if st.button("Cancel"):
                del st.session_state["_confirm_clear_at"]
                st.rerun()
