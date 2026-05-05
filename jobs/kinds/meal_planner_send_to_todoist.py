"""Phase 14.10 — Send scaled grocery lines to Todoist (no consolidation).

For each selected recipe, scales ingredients to the requested serving count
and creates one Todoist task per ingredient. Ingredients are NOT merged across
recipes; duplicates appear as separate tasks with a (Recipe Name) suffix.
"""
from __future__ import annotations

import json
import logging
import os

from jobs import huey
from jobs.adapters import todoist as todoist_adapter
from meal_planner.queries import get_recipe
from meal_planner.scaling import scale_ingredients

logger = logging.getLogger(__name__)


@huey.task()
def meal_planner_send_to_todoist(recipe_scales: list[list]) -> dict:
    """Send raw scaled grocery lines to Todoist.

    recipe_scales: list of [recipe_id, target_servings] pairs
    (JSON-serialised as lists, not tuples).

    Required env vars:
        TODOIST_SECTIONS   — JSON object mapping section name → section_id

    Optional:
        TODOIST_PROJECT_ID — target Todoist project; defaults to inbox
    """
    sections: dict[str, str] = json.loads(os.environ["TODOIST_SECTIONS"])
    fallback_name: str = next(iter(sections))

    project_id = os.environ.get("TODOIST_PROJECT_ID")
    sent = 0
    attempted = 0

    for rid, target_servings in recipe_scales:
        recipe = get_recipe(int(rid))
        scaled = scale_ingredients(recipe, int(target_servings))

        for ingredient in scaled:
            attempted += 1

            qty = ingredient.qty_per_serving  # already multiplied by target_servings
            if qty is not None:
                qty_str = f"{qty:.4g}"
                if ingredient.unit:
                    base = f"{qty_str} {ingredient.unit} {ingredient.name}"
                else:
                    base = f"{qty_str} {ingredient.name}"
            else:
                base = ingredient.name
            title = f"{base.strip()} ({recipe.title})"

            section_name = (
                ingredient.todoist_section
                if ingredient.todoist_section in sections
                else fallback_name
            )
            section_id = sections[section_name]

            result = todoist_adapter.create_task(
                output_config={
                    "project_id": project_id,
                    "section_id": section_id,
                    "labels": ["meal-planner"],
                },
                payload={
                    "title": title,
                    "source": "meal-planner",
                    "source_id": f"recipes:{recipe.id}",
                    "priority": "normal",
                    "confidence": 1.0,
                },
            )
            if result.get("created"):
                sent += 1

    logger.info(
        "meal_planner_send_to_todoist: sent %d/%d items", sent, attempted
    )
    return {"items_sent": sent, "items_attempted": attempted}
