#!/usr/bin/env python3
"""
Consolidate the Todoist grocery list.

Only tasks with the 'meal-planner' label are touched.
Tasks added manually (without that label) are never read, modified, or deleted.

Usage:
    python consolidate.py              # shows diff, prompts to confirm
    python consolidate.py --yes        # non-interactive (skip confirmation)
    python consolidate.py --dry-run    # print result but make no changes
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

_here = Path(__file__).parent
load_dotenv(_here / ".env")
load_dotenv(_here.parent / ".env")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        sys.exit(f"Error: required environment variable '{key}' is not set. See .env.example.")
    return val


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Todoist API helpers
# ---------------------------------------------------------------------------

def fetch_labeled_tasks(token: str, project_id: str, label: str) -> list[dict]:
    """Fetch all tasks with the given label, handling cursor-based pagination."""
    headers = {"Authorization": f"Bearer {token}"}
    tasks: list[dict] = []
    cursor = None

    while True:
        params: dict = {"project_id": project_id, "label": label}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            "https://api.todoist.com/api/v1/tasks",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        tasks.extend(data.get("results", []))
        cursor = data.get("next_cursor")
        if not cursor:
            break

    return tasks


def delete_task(token: str, task_id: str) -> None:
    resp = requests.delete(
        f"https://api.todoist.com/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()


def create_task(
    token: str,
    content: str,
    project_id: str,
    section_id: str,
    label: str,
) -> None:
    resp = requests.post(
        "https://api.todoist.com/api/v1/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content": content,
            "project_id": project_id,
            "section_id": section_id,
            "labels": [label],
        },
        timeout=15,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Consolidation via Claude
# ---------------------------------------------------------------------------

def consolidate_via_gemini(
    tasks: list[dict],
    sections: dict[str, str],
    api_key: str,
) -> list[dict]:
    """Return consolidated list as [{content, section}, ...]."""
    ingredient_lines = "\n".join(f"- {t['content']}" for t in tasks)
    section_names = list(sections.keys())
    fallback = section_names[0]

    prompt = (
        f"You are a grocery list assistant. Consolidate this ingredient list:\n"
        f"- Combine duplicate or equivalent ingredients into one entry\n"
        f"- Sum quantities where possible (e.g. '1 cup olive oil' + '2 tbsp olive oil' → '1 cup + 2 tbsp olive oil')\n"
        f"- Assign each item to one of these sections: {', '.join(section_names)}\n"
        f"- Keep the format 'quantity unit ingredient' (e.g. '2 cups flour')\n\n"
        f"Ingredients:\n{ingredient_lines}\n\n"
        f"Respond with a JSON array only — no other text:\n"
        f'[{{"content": "...", "section": "..."}}, ...]\n\n'
        f'Use the exact section names provided. If unsure, use "{fallback}".'
    )

    resp = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=30,
    )
    resp.raise_for_status()

    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        sys.exit("Error: could not parse Gemini's response. Try running again.")

    return json.loads(text[start:end])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consolidate meal-planner-labeled tasks in the Todoist grocery list."
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print consolidated list without making changes"
    )
    parser.add_argument(
        "--clear", action="store_true", help="Delete all labeled tasks without consolidating"
    )
    args = parser.parse_args()

    token = _require("TODOIST_API_TOKEN")
    project_id = _require("TODOIST_PROJECT_ID")
    sections_json = _require("TODOIST_SECTIONS")
    if not args.clear:
        api_key = _require("GEMINI_API_KEY")
    label = _get("TODOIST_LABEL", "meal-planner")

    sections: dict[str, str] = json.loads(sections_json)

    print(f"Fetching tasks with label '{label}' from Todoist…")
    tasks = fetch_labeled_tasks(token, project_id, label)

    if not tasks:
        print(f"No tasks with label '{label}' found. Nothing to do.")
        return 0

    if args.clear:
        if not args.yes:
            answer = input(f"Delete all {len(tasks)} meal-planner tasks? [y/N] ")
            if answer.strip().lower() != "y":
                print("Aborted.")
                return 0
        print(f"Deleting {len(tasks)} tasks…")
        for task in tasks:
            delete_task(token, task["id"])
        print("Done.")
        return 0

    print(f"Found {len(tasks)} tasks. Consolidating with Claude…")
    consolidated = consolidate_via_gemini(tasks, sections, api_key)

    # Print consolidated list
    print(f"\nConsolidated list ({len(consolidated)} items, down from {len(tasks)}):")
    for item in consolidated:
        print(f"  [{item['section']}] {item['content']}")

    if args.dry_run:
        print("\n(dry-run — no changes made)")
        return 0

    if not args.yes:
        answer = input(
            f"\nReplace {len(tasks)} tasks with {len(consolidated)} consolidated tasks? [y/N] "
        )
        if answer.strip().lower() != "y":
            print("Aborted.")
            return 0

    print(f"\nDeleting {len(tasks)} existing tasks…")
    for task in tasks:
        delete_task(token, task["id"])

    print(f"Creating {len(consolidated)} consolidated tasks…")
    unknown_sections: set[str] = set()
    fallback_section_id = next(iter(sections.values()))

    for item in consolidated:
        section_id = sections.get(item["section"])
        if not section_id:
            unknown_sections.add(item["section"])
            section_id = fallback_section_id
        create_task(token, item["content"], project_id, section_id, label)

    if unknown_sections:
        first_section = list(sections.keys())[0]
        print(
            f"Warning: Claude used unknown section(s) {unknown_sections}. "
            f"Those items were placed in '{first_section}'."
        )

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
