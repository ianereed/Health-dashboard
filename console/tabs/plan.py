"""Recipes tab — multi-recipe grid with Send-to-Todoist (Phase 14.9).

Renders an editable grid of all recipes. Each row has a Send checkbox and a
Servings input. Clicking "Send checked recipes to Todoist" consolidates the
selected recipes via Gemini and creates one Todoist task per grocery line.
"""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from console import jobs_client as _jobs_client
from meal_planner import db as _db
from meal_planner import queries
from meal_planner.tag_categories import CATEGORY_MAP, _partition_tags_by_category

from console.tabs._job_status import (
    _format_status,
    _read_result_or_synthesize_error,
)

_CONFIRM_CLEAR_TTL = 10  # seconds before the confirm state resets

__all__ = ["render", "_format_status", "_read_result_or_synthesize_error"]


def render() -> None:
    try:
        _render_inner()
    except Exception as exc:
        st.error("Plan tab error — see traceback below")
        st.exception(exc)


@st.fragment(run_every="2s")
def _render_job_status(state_key: str, label: str) -> None:
    """Poll jobs_client for the job stored at session_state[state_key].

    Renders a spinner while pending; renders terminal status (success/warning/
    error) with the result-dict summary when complete. Clears state_key on
    terminal render so the fragment stops re-running.
    """
    state = st.session_state.get(state_key)
    if not state:
        return
    task_id = state["task_id"]
    started_at = state["started_at"]
    result = _read_result_or_synthesize_error(_jobs_client.result, task_id)
    if result is None:
        elapsed = int(time.monotonic() - started_at)
        st.info(f"{label}… ({elapsed}s)", icon="⏳")
        return
    # terminal — render and clear
    del st.session_state[state_key]
    level, message = _format_status(result)
    if level == "success":
        st.success(f"{label}: {message}")
    elif level == "warning":
        st.warning(f"{label}: {message}")
    else:
        st.error(f"{label}: {message}")


def _render_inner() -> None:
    if not _db.DB_PATH.exists():
        st.info(
            "**No recipes seeded yet.**\n\n"
            "Run `python -m meal_planner.seed_from_sheet` on the mini to populate "
            "the recipe database, then refresh."
        )
        return

    all_tags = queries.list_all_tags()
    if all_tags:
        grouped = _partition_tags_by_category(all_tags, CATEGORY_MAP)
        selected: list[str] = []
        if grouped["cuisine"]:
            selected += st.pills(
                "Cuisine", options=grouped["cuisine"], selection_mode="multi",
                key="tag_pills_cuisine",
            ) or []
        if grouped["meat_or_diet"]:
            selected += st.pills(
                "Meat / diet", options=grouped["meat_or_diet"],
                selection_mode="multi", key="tag_pills_meat",
            ) or []
        if grouped["other"]:
            selected += st.pills(
                "Other", options=grouped["other"], selection_mode="multi",
                key="tag_pills_other",
            ) or []
        selected_tags = selected
        tag_logic = st.radio(
            "Match", ["AND", "OR"], horizontal=True, index=0
        )
    else:
        selected_tags = []
        tag_logic = "AND"

    sort_alpha = st.toggle(
        "Alphabetical", value=True, key="recipes_sort_alpha",
        help="When off, recipes are listed most-recently-added first.",
    )
    recipes = queries.search_recipes(
        tags=tuple(selected_tags),
        tag_logic=tag_logic.lower(),
        sort="alpha" if sort_alpha else "recent",
    )
    if not recipes:
        if selected_tags:
            st.info(
                "No recipes match the current tag filter. "
                "Adjust selection above."
            )
            return
        st.info("Recipe database exists but contains no recipes yet.")
        return

    recipe_ids = [r.id for r in recipes]
    df = pd.DataFrame({
        "Send": [False] * len(recipes),
        "Recipe": [r.title for r in recipes],
        "Servings": [r.base_servings for r in recipes],
    })

    edited_df = st.data_editor(
        df,
        column_config={
            "Send": st.column_config.CheckboxColumn("Send"),
            "Recipe": st.column_config.TextColumn("Recipe"),
            "Servings": st.column_config.NumberColumn(
                "Servings", min_value=1, max_value=20, step=1
            ),
        },
        disabled=["Recipe"],
        num_rows="fixed",
        use_container_width=True,
        hide_index=True,
    )

    if st.button(
        "Send checked recipes to Todoist", type="primary", use_container_width=True
    ):
        checked = [
            [recipe_ids[i], int(row["Servings"])]
            for i, row in edited_df.iterrows()
            if row["Send"]
        ]
        if not checked:
            st.warning("No recipes selected. Check at least one box.")
        else:
            try:
                task_id = _jobs_client.enqueue(
                    "meal_planner_send_to_todoist", {"checked": checked}
                )
                st.session_state["_send_job"] = {
                    "task_id": task_id,
                    "started_at": time.monotonic(),
                }
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to enqueue: {exc}")

    _render_job_status("_send_job", "Send to Todoist")

    st.divider()
    _render_clear_button()
    _render_job_status("_clear_job", "Clear Todoist")


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
                    task_id = _jobs_client.enqueue("meal_planner_clear_todoist")
                    st.session_state["_clear_job"] = {
                        "task_id": task_id,
                        "started_at": time.monotonic(),
                    }
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to enqueue: {exc}")
        with col_no:
            if st.button("Cancel"):
                del st.session_state["_confirm_clear_at"]
                st.rerun()
