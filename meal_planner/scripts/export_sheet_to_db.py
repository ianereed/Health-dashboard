"""
Compare the Google Sheet against recipes.db and optionally import new recipes.

Default mode (dry-run):
    Prints a diff report — Sheet-only, DB-only, ingredient-count-mismatch.

With --apply:
    Imports Sheet-only recipes into recipes.db via Gemini categorization.
    Each insert is logged to stdout and to
    ~/Home-Tools/logs/export-sheet-<utc>-apply.log.

Run on the mini:
    cd ~/Home-Tools
    python -m meal_planner.scripts.export_sheet_to_db           # dry-run
    python -m meal_planner.scripts.export_sheet_to_db --apply   # live import

Required env vars (same as seed_from_sheet.py):
    MEAL_PLANNER_SHEET_ID
    GOOGLE_SERVICE_ACCOUNT_PATH
    GEMINI_API_KEY (only needed when --apply is used)

Optional:
    TODOIST_SECTIONS  — JSON map of section names to IDs (Gemini categorization)
    SEED_DELAY        — seconds between Gemini calls (default: 3)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from meal_planner import db as _db
from meal_planner.db import add_recipe_tag, init_db, insert_recipe
from meal_planner.queries import list_ingredients, list_recipes
from meal_planner.seed_from_sheet import (
    _DEFAULT_SECTIONS,
    _get,
    _get_recipes_from_worksheet,
    _insert_ingredients_batch,
    _load_env,
    _open_sheet,
    _parse_ingredients,
    _require,
)

_LOG_DIR = Path.home() / "Home-Tools" / "logs"


def _setup_logging(dry_run: bool) -> logging.Logger:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode = "dryrun" if dry_run else "apply"
    log_path = _LOG_DIR / f"export-sheet-{ts}-{mode}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("export_sheet")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f"Log: {log_path}")
    return logger


# ---------------------------------------------------------------------------
# Core diff (pure — testable without gspread or DB)
# ---------------------------------------------------------------------------

def compute_diff(
    sheet_recipes: list[tuple[str, str, list[str]]],
    db_by_title: dict[str, tuple[int, str, int]],
) -> dict:
    """Compute diff between Sheet recipes and DB.

    sheet_recipes: list of (tab_name, title, ingredient_strings)
    db_by_title:   {lower_title: (recipe_id, original_title, ingredient_count)}

    Returns:
        {
          "only_in_sheet": [(tab, title, ingredients), ...],
          "only_in_db":    [(recipe_id, title), ...],
          "mismatch":      [(tab, title, sheet_count, db_count), ...],
        }
    """
    sheet_by_lower: dict[str, tuple[str, str, list[str]]] = {}
    for tab, title, ings in sheet_recipes:
        key = title.strip().lower()
        if key:
            sheet_by_lower[key] = (tab, title, ings)

    only_in_sheet: list[tuple[str, str, list[str]]] = []
    mismatch: list[tuple[str, str, int, int]] = []

    for lower_key, (tab, title, ings) in sheet_by_lower.items():
        if lower_key not in db_by_title:
            only_in_sheet.append((tab, title, ings))
        else:
            _recipe_id, _db_title, db_ing_count = db_by_title[lower_key]
            sheet_count = len(ings)
            if sheet_count != db_ing_count:
                mismatch.append((tab, title, sheet_count, db_ing_count))

    only_in_db: list[tuple[int, str]] = [
        (recipe_id, db_title)
        for lower_key, (recipe_id, db_title, _) in db_by_title.items()
        if lower_key not in sheet_by_lower
    ]

    return {
        "only_in_sheet": only_in_sheet,
        "only_in_db": only_in_db,
        "mismatch": mismatch,
    }


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------

def build_db_index(db_path: Path) -> dict[str, tuple[int, str, int]]:
    """Return {lower_title: (recipe_id, title, ingredient_count)} from DB."""
    index: dict[str, tuple[int, str, int]] = {}
    for recipe in list_recipes(path=db_path):
        ing_count = len(list_ingredients(recipe.id, path=db_path))
        index[recipe.title.strip().lower()] = (recipe.id, recipe.title, ing_count)
    return index


def build_sheet_index(
    sheet_id: str, service_account_path: str
) -> list[tuple[str, str, list[str]]]:
    """Return [(tab_name, title, ingredients), ...] from the live Sheet."""
    spreadsheet = _open_sheet(sheet_id, service_account_path)
    recipes: list[tuple[str, str, list[str]]] = []
    for ws in spreadsheet.worksheets():
        if ws.title.lower() == "readme":
            continue
        for title, _col_idx, ings in _get_recipes_from_worksheet(ws):
            recipes.append((ws.title, title, ings))
    return recipes


# ---------------------------------------------------------------------------
# Report + apply
# ---------------------------------------------------------------------------

def print_report(diff: dict, logger: logging.Logger) -> None:
    only_sheet = diff["only_in_sheet"]
    only_db = diff["only_in_db"]
    mismatch = diff["mismatch"]

    logger.info("")
    logger.info("=" * 60)
    logger.info("SHEET vs DB DIFF REPORT")
    logger.info("=" * 60)

    logger.info(f"\nIn Sheet, NOT in DB ({len(only_sheet)} recipe(s) — would be imported with --apply):")
    if only_sheet:
        for tab, title, ings in only_sheet:
            logger.info(f"  [{tab}] {title!r}  ({len(ings)} ingredient(s))")
    else:
        logger.info("  (none)")

    logger.info(f"\nIn DB, NOT in Sheet ({len(only_db)} recipe(s) — informational):")
    if only_db:
        for _rid, title in only_db:
            logger.info(f"  {title!r}")
    else:
        logger.info("  (none)")

    logger.info(f"\nTitle match, ingredient count differs ({len(mismatch)} recipe(s)):")
    if mismatch:
        for tab, title, s_count, db_count in mismatch[:3]:
            logger.info(f"  [{tab}] {title!r}: Sheet={s_count}, DB={db_count}")
        if len(mismatch) > 3:
            logger.info(f"  … and {len(mismatch) - 3} more")
    else:
        logger.info("  (none)")

    logger.info("")


def apply_imports(
    only_in_sheet: list[tuple[str, str, list[str]]],
    api_key: str,
    section_names: list[str],
    delay: float,
    db_path: Path,
    logger: logging.Logger,
) -> tuple[int, int]:
    """Import Sheet-only recipes into DB. Returns (imported_count, failed_count)."""
    imported = 0
    failed = 0
    total = len(only_in_sheet)

    for i, (tab, title, ingredient_strings) in enumerate(only_in_sheet, 1):
        prefix = f"[{i}/{total}] {title!r} (tab={tab!r})"
        logger.info(f"{prefix} — calling Gemini…")

        if i > 1 and delay > 0:
            time.sleep(delay)

        base_servings = 4
        try:
            parsed = _parse_ingredients(
                title, base_servings, ingredient_strings, section_names, api_key
            )
        except Exception as exc:
            # _call_gemini doesn't wrap requests.post; a transient network error
            # (ConnectionError, Timeout) would otherwise kill the whole batch.
            logger.info(f"{prefix} — GEMINI CALL FAILED: {exc}, skipping")
            failed += 1
            continue
        if parsed is None:
            logger.info(f"{prefix} — PARSE FAILED, skipping")
            failed += 1
            continue

        tag = tab.strip().lower()
        conn = _db._get_conn(db_path)
        try:
            existing = conn.execute(
                "SELECT id FROM recipes WHERE LOWER(title) = LOWER(?)",
                (title,),
            ).fetchone()
            if existing:
                logger.info(f"{prefix} — title already in DB (id={existing[0]}), skipping")
                failed += 1
                continue
            recipe_id = insert_recipe(
                title=title,
                base_servings=base_servings,
                path=db_path,
                conn=conn,
            )
            ing_count, warnings = _insert_ingredients_batch(
                recipe_id=recipe_id,
                parsed=parsed,
                base_servings=base_servings,
                path=db_path,
                conn=conn,
            )
            add_recipe_tag(recipe_id, tag, path=db_path, conn=conn)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.info(f"{prefix} — DB INSERT FAILED: {exc}, skipping")
            failed += 1
            continue
        finally:
            conn.close()

        logger.info(f"{prefix} — inserted recipe_id={recipe_id}, {ing_count} ingredient(s)")
        for w in warnings:
            logger.info(f"  WARNING: {w}")
        imported += 1

    return imported, failed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    _load_env()

    parser = argparse.ArgumentParser(
        description="Compare Google Sheet vs recipes.db and optionally import new recipes."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Import Sheet-only recipes into DB (default: dry-run, report only).",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    logger = _setup_logging(dry_run)

    sheet_id = _require("MEAL_PLANNER_SHEET_ID")
    service_account_path = _require("GOOGLE_SERVICE_ACCOUNT_PATH")

    db_path = _db.DB_PATH
    init_db(db_path)

    logger.info(f"DB:    {db_path}")
    logger.info(f"Sheet: {sheet_id[:8]}…")
    logger.info(f"Mode:  {'DRY-RUN (pass --apply to import)' if dry_run else 'APPLY — importing new recipes'}")

    logger.info("\nReading Sheet…")
    sheet_recipes = build_sheet_index(sheet_id, service_account_path)
    logger.info(f"  {len(sheet_recipes)} recipe(s) found in Sheet.")

    logger.info("Reading DB…")
    db_index = build_db_index(db_path)
    logger.info(f"  {len(db_index)} recipe(s) found in DB.")

    diff = compute_diff(sheet_recipes, db_index)
    print_report(diff, logger)

    if dry_run:
        only_sheet_count = len(diff["only_in_sheet"])
        if only_sheet_count:
            logger.info(f"Dry-run complete. Run with --apply to import {only_sheet_count} recipe(s).")
        else:
            logger.info("Dry-run complete. Sheet and DB are in sync.")
        return 0

    # --apply path
    sections_json = _get("TODOIST_SECTIONS", "")
    if sections_json:
        try:
            section_names = list(json.loads(sections_json).keys())
        except json.JSONDecodeError:
            logger.info("Warning: TODOIST_SECTIONS is not valid JSON — using defaults")
            section_names = _DEFAULT_SECTIONS
    else:
        section_names = _DEFAULT_SECTIONS

    api_key = _require("GEMINI_API_KEY")
    delay = float(_get("SEED_DELAY", "3"))

    only_in_sheet = diff["only_in_sheet"]
    if not only_in_sheet:
        logger.info("Nothing to import — Sheet and DB are already in sync.")
        return 0

    logger.info(f"Importing {len(only_in_sheet)} recipe(s)…")
    imported, failed = apply_imports(
        only_in_sheet=only_in_sheet,
        api_key=api_key,
        section_names=section_names,
        delay=delay,
        db_path=db_path,
        logger=logger,
    )
    logger.info(f"\nDone. Imported: {imported}, Failed/skipped: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
