"""Phase 14.5 — Send consolidated grocery list to Todoist.

Reads TODOIST_SECTIONS (JSON name→section_id map), scales each recipe,
consolidates via Gemini, then creates one Todoist task per GroceryLine.

labels defaults to ["event-aggregator"] if omitted from output_config;
this Job kind overrides explicitly so meal-planner tasks land under the
meal-planner label rather than the event-aggregator label.
"""
from __future__ import annotations

import json
import logging
import os

from jobs import huey
from jobs.adapters import todoist as todoist_adapter
from meal_planner.consolidation import consolidate_for_grocery
from meal_planner.queries import get_recipe

logger = logging.getLogger(__name__)


@huey.task()
def meal_planner_send_to_todoist(recipe_scales: list[list]) -> dict:
    """Send a consolidated grocery list to Todoist.

    recipe_scales: list of [recipe_id, target_servings] pairs
    (JSON-serialised as lists, not tuples).

    Required env vars:
        TODOIST_SECTIONS   — JSON object mapping section name → section_id
        GEMINI_API_KEY     — Gemini API key for consolidation

    Optional:
        TODOIST_PROJECT_ID — target Todoist project; defaults to inbox

    labels defaults to ["event-aggregator"] if omitted from output_config;
    this Job kind overrides explicitly so meal-planner tasks land under the
    meal-planner label rather than the event-aggregator label.
    """
    sections: dict[str, str] = json.loads(os.environ["TODOIST_SECTIONS"])
    api_key: str = os.environ["GEMINI_API_KEY"]
    fallback_name: str = next(iter(sections))

    items = [(get_recipe(int(rid)), int(servings)) for rid, servings in recipe_scales]
    section_names = list(sections.keys())

    grocery = consolidate_for_grocery(items, sections=section_names, api_key=api_key)

    project_id = os.environ.get("TODOIST_PROJECT_ID")
    sent = 0

    for line in grocery:
        if line.qty is not None:
            qty_str = f"{line.qty:.4g}"
            title = f"{qty_str} {line.unit} {line.name}".strip() if line.unit else f"{qty_str} {line.name}".strip()
        else:
            title = line.name

        section_name = line.todoist_section if line.todoist_section in sections else fallback_name
        section_id = sections[section_name]

        recipe_ids_str = ",".join(str(r.id) for r, _ in items)
        result = todoist_adapter.create_task(
            output_config={
                "project_id": project_id,
                "section_id": section_id,
                "labels": ["meal-planner"],
            },
            payload={
                "title": title,
                "source": "meal-planner",
                "source_id": f"recipes:{recipe_ids_str}",
                "priority": "normal",
                "confidence": 1.0,
            },
        )
        if result.get("created"):
            sent += 1

    logger.info(
        "meal_planner_send_to_todoist: sent %d/%d items", sent, len(grocery)
    )
    return {"items_sent": sent, "items_attempted": len(grocery)}
