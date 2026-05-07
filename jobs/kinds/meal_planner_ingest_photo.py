"""Phase 16 Chunk 2 — Extract recipe from a NAS photo and seed the DB.

Triggered by meal_planner_photo_intake_scan for each new photo sha.
On success: inserts recipe row + tag + ingredients; moves file to _done/.
On non-ok extraction: records error in photos_intake, leaves file in _processing/.
Card UX (Chunk 3) and wedge logic (Chunk 4) are not yet wired.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from jobs import huey, requires, requires_model
from meal_planner import db as _db
from meal_planner.db import add_recipe_tag, insert_recipe
from meal_planner.eval.preprocess_images import _process_one
from meal_planner.seed_from_sheet import _insert_ingredients_batch
from meal_planner.vision import intake_db
from meal_planner.vision.extract import extract_recipe_from_photo

logger = logging.getLogger(__name__)

_DEFAULT_INTAKE_DIR = "/Users/homeserver/Share1/Documents/Recipes/photo-intake"


@huey.task(retries=2, retry_delay=60)
@requires_model("vision", keep_alive=300, batch_hint="drain")
@requires(["fs:meal_planner", "model:llama3.2-vision:11b"])
def meal_planner_ingest_photo(sha: str) -> dict:
    row = intake_db.get_by_sha(sha)
    if row is None or row.status != "pending":
        logger.info("meal_planner_ingest_photo: sha=%s status=%s — skip", sha, row.status if row else "missing")
        return {"sha": sha, "status": "skipped_already_handled", "recipe_id": None, "latency_s": None}

    intake_db.mark_status(sha, "extracting")

    nas_path = Path(row.nas_path)
    intake_dir = Path(os.environ.get("MEAL_PLANNER_NAS_INTAKE_DIR", _DEFAULT_INTAKE_DIR))
    done_dir = intake_dir / "_done"
    done_path = done_dir / f"{sha}.jpg"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        preprocessed = tmp / f"{sha}.jpg"
        _process_one(
            src=nas_path,
            dst=preprocessed,
            max_dim=1500,
            autocontrast_cutoff=2,
            log_path=tmp / "preprocess.log",
        )
        result = extract_recipe_from_photo(
            preprocessed,
            timeout_s=500,
            num_ctx=4096,
            keep_alive="300s",
        )

    if result.status == "ok":
        db_path = _db.DB_PATH
        conn = _db._get_conn(db_path)
        try:
            title = (result.parsed.get("title") or "") or sha
            recipe_id = insert_recipe(
                title=title,
                source="nas-intake",
                photo_path=str(done_path),
                conn=conn,
            )
            add_recipe_tag(recipe_id, "photo-intake", conn=conn)
            _insert_ingredients_batch(
                recipe_id=recipe_id,
                parsed=result.parsed.get("ingredients", []),
                base_servings=4,
                path=db_path,
                conn=conn,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        done_dir.mkdir(parents=True, exist_ok=True)
        nas_path.rename(done_path)
        intake_db.mark_status(sha, "ok", recipe_id=recipe_id, extraction_path="ollama")
        logger.info("meal_planner_ingest_photo: ok sha=%s recipe_id=%d", sha, recipe_id)
        return {"sha": sha, "status": "ok", "recipe_id": recipe_id, "latency_s": result.latency_s}

    intake_db.mark_status(sha, result.status, error=result.error)
    logger.warning(
        "meal_planner_ingest_photo: %s sha=%s error=%s",
        result.status, sha, (result.error or "")[:200],
    )
    return {"sha": sha, "status": result.status, "recipe_id": None, "latency_s": result.latency_s}
