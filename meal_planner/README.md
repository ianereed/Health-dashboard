# meal_planner

Meal planning system for the household. Phase 14 V0 ships a recipe browser tab
in the Mini Ops console with a Send-to-Todoist grocery list flow.

## What it is

```
  Google Sheet (legacy — kept as fallback through Phase 18)
        │
        ▼
  seed_from_sheet.py  (Gemini batch) → recipes.db
        │
        ▼
  console/tabs/plan.py  (Streamlit Recipes tab at :8503/?tab=recipes)
        │
        ▼
  meal_planner_send_to_todoist Job kind → scale_ingredients() → Todoist tasks (one per ingredient)
```

Phase 14 introduced the Python package (renamed from `meal-planner/`) and
wired the entire flow from Sheet seed to Todoist write. The Apps Script
frontend still works as a read-only fallback; it will be decommissioned in
Phase 18.

## Audience

Joint (Anny + Ian). LAN + Tailscale only. No external auth.

## Deep-link URL

```
http://homeserver:8503/?tab=recipes
```

Use the explicit `?tab=recipes` parameter — tab clicks don't update the URL
(Streamlit st.tabs limitation). Send this URL to Anny, not the bare `/`.

## Status

**Phase 14 V0 live (2026-05-05).** 16 recipes seeded from the existing Sheet.
Multi-recipe grid (st.data_editor): check one or more recipes, adjust servings,
click "Send checked recipes to Todoist". Creates one Todoist task per scaled
ingredient under the `meal-planner` label. Ingredients are NOT merged across
recipes — duplicates appear as separate tasks, each tagged with `(Recipe Name)`
so you can tell them apart. No Gemini call on send; Gemini consolidation is
available in `consolidation.py` for a future opt-in phase. "Clear all
meal-planner items from Todoist" button available for cleanup. Tag filter (Phase 17) — three labeled pill rows (Cuisine / Meat+diet / Other)
plus AND/OR radio. Empty selection = show all. `st.toggle("Alphabetical")`
above the grid: on = alpha by title (default, session-only), off = most-recently-added first.

**Phase 15 done (2026-05-06)** — bake-off picked `llama3.2-vision:11b` via
Ollama on the mini for recipe-photo extraction. See
`meal_planner/eval/PHASE15_NOTES.md` and `meal_planner/eval/bake_off.py`.

**Phase 16 done (2026-05-07)** — Recipe-photo intake live. Drop a JPG/PDF in
`Share1/Documents/Recipes/photo-intake/`; the mini extracts → normalizes →
inserts the recipe + ingredients + tags into the DB and renames to `_done/`.
Job kinds: `meal_planner_photo_intake_scan` + `meal_planner_ingest_photo`.
Post-extraction normalizer at `meal_planner/vision/_normalize.py` fixes the
qty/unit-fusion class of LLM bugs deterministically.

Phase 17 direction (UI polish) and Phase 18 (jobs-queue bug fix —
nas_intake_scan worker starvation + streamlit orphan-WAL-fd silent
drops): `Mac-mini/PLAN.md`.

## ⚠️ Critical model rules

| Task | Model | Why |
|------|-------|-----|
| Recipe categorization | `gemini-2.5-flash-lite` | RPD headroom for batch volume |
| Pantry consolidation | `gemini-2.5-flash-lite` | Same |
| Bulk recipe import | `gemini-2.5-flash-lite` | Same |
| Single-photo recipe vision | `gemini-2.5-flash` | Vision quality |
| ❌ ANY task | `gemini-1.5-flash` | DOES NOT WORK — don't use |

## Package layout

```
meal_planner/
  __init__.py
  db.py               — SQLite schema, init_db, insert_recipe/ingredient
  models.py           — Recipe, Ingredient, GroceryLine dataclasses
  queries.py          — list_recipes(), get_recipe()
  scaling.py          — scale_ingredients(recipe, target_servings)
  consolidation.py    — consolidate_for_grocery() via Gemini
  seed_from_sheet.py  — one-shot importer from Google Sheet
  legacy/             — archived Apps Script + old consolidate.py
  tests/
apps-script/          — legacy Google Apps Script source (read-only fallback)
```

Job kinds:
- `jobs/kinds/meal_planner_send_to_todoist.py` — creates grocery tasks in Todoist
- `jobs/kinds/meal_planner_clear_todoist.py` — deletes all tasks labeled `meal-planner`

The Todoist label (`meal-planner`) is a **code constant** in `meal_planner_clear_todoist.py`,
not an env var. This is intentional — the label is the safety boundary that prevents the
clear job from touching event-aggregator or finance-monitor tasks.

## Env vars (meal_planner/.env on mini)

| Var | Required | Notes |
|-----|----------|-------|
| `GEMINI_API_KEY` | yes | consolidation + seed categorization |
| `TODOIST_API_TOKEN` | yes | pulled from keychain in consumer |
| `TODOIST_SECTIONS` | yes | JSON map of section name → section_id |
| `TODOIST_PROJECT_ID` | no | defaults to Todoist inbox |
| `MEAL_PLANNER_SHEET_ID` | seed only | Google Sheet ID |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | seed only | path to service account JSON |

## Running the seeder

```bash
cd ~/Home-Tools
source meal_planner/.env
python -m meal_planner.seed_from_sheet
```

This hits the live Google Sheet and has a Gemini API cost. Don't run in CI.

## Reference

- `Mac-mini/PLAN.md` — Phase 15+ roadmap
- Memory: `project_meal_planner.md`, `project_meal_planner_expansion_priority.md`
- Design doc: `~/.gstack/projects/ianereed-Home-Tools/ianereed-main-design-20260501-132248.md`
- LLM bake-off (Phase 15): [`meal_planner/eval/README.md`](eval/README.md)
