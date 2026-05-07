"""Phase 16 Chunk 2 — Discover new recipe photos in the NAS drop zone.

Every 5 minutes:
1. Walks MEAL_PLANNER_NAS_INTAKE_DIR for .jpg/.jpeg/.png files.
2. SHA-256-dedup: skips any file whose content hash is already in photos_intake.
3. Renames accepted files to _processing/<sha>.jpg (atomic on same FS).
4. Inserts a pending row in photos_intake.
5. Enqueues meal_planner_ingest_photo(sha) for extraction.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from huey import crontab

from jobs import huey, requires
from jobs.kinds.meal_planner_ingest_photo import meal_planner_ingest_photo
from meal_planner.vision import intake_db

logger = logging.getLogger(__name__)

_DEFAULT_INTAKE_DIR = "/Users/homeserver/Share1/Documents/Recipes/photo-intake"
_IMAGE_SUFFIXES = frozenset({".jpg", ".JPG", ".jpeg", ".JPEG", ".png", ".PNG"})
_SUBFOLDERS = ("_processing", "_done", "_skipped", "_wedged")


def _sha256_hex16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


@huey.periodic_task(crontab(minute="*/5"))
@requires(["fs:meal_planner"])
def meal_planner_photo_intake_scan() -> dict:
    intake_dir = Path(os.environ.get("MEAL_PLANNER_NAS_INTAKE_DIR", _DEFAULT_INTAKE_DIR))

    try:
        files = list(intake_dir.iterdir())
    except OSError as exc:
        logger.warning("meal_planner_photo_intake_scan: drop zone unreachable: %s", exc)
        return {
            "discovered": 0,
            "enqueued": 0,
            "skipped_dup": 0,
            "tick_at": datetime.now(timezone.utc).isoformat(),
        }

    for sub in _SUBFOLDERS:
        (intake_dir / sub).mkdir(parents=True, exist_ok=True)

    discovered = 0
    enqueued = 0
    skipped_dup = 0

    for f in files:
        if not f.is_file():
            continue
        if f.suffix not in _IMAGE_SUFFIXES:
            continue

        discovered += 1
        sha = _sha256_hex16(f)
        target = intake_dir / "_processing" / f"{sha}.jpg"

        existing = intake_db.get_by_sha(sha)
        if existing is not None:
            logger.info(
                "meal_planner_photo_intake_scan: dup sha=%s file=%s status=%s",
                sha, f.name, existing.status,
            )
            skipped_dup += 1
            continue

        f.rename(target)
        intake_db.record_intake(sha, source_path=f.name, nas_path=str(target))
        meal_planner_ingest_photo(sha)
        enqueued += 1
        logger.info("meal_planner_photo_intake_scan: enqueued sha=%s", sha)

    return {
        "discovered": discovered,
        "enqueued": enqueued,
        "skipped_dup": skipped_dup,
        "tick_at": datetime.now(timezone.utc).isoformat(),
    }
