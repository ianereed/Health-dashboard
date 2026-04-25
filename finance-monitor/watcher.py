"""
Scan the intake/ folder for new YNAB CSV exports and PDF documents.
Imports each file, then moves it to imported/YYYY-MM/.
Runs once and exits (invoked by a 5-minute interval LaunchAgent).
"""
import fcntl
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
import db
from ingest import image_importer, pdf_importer, ynab_api, ynab_csv

_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".heic", ".heif", ".tiff", ".tif", ".webp", ".gif"})

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _dest_dir() -> Path:
    month = datetime.now(tz=timezone.utc).strftime("%Y-%m")
    d = config.IMPORTED_DIR / month
    d.mkdir(parents=True, exist_ok=True)
    return d


def run() -> None:
    # launchd's StartInterval fires on wall-clock; if a previous tick is still
    # OCRing, a second instance would race on intake/ files and the SQLite
    # writer. Hold a non-blocking flock for the lifetime of this run.
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = config.DB_PATH.parent / "watcher.lock"
    lock_fp = open(lock_path, "w")
    try:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.info("watcher: another instance is running — exiting")
        lock_fp.close()
        return

    db.init_db()
    config.INTAKE_DIR.mkdir(parents=True, exist_ok=True)

    status = ynab_api.sync()
    logger.info("watcher: ynab sync → %s", status)

    files = list(config.INTAKE_DIR.iterdir())
    if not files:
        logger.info("watcher: intake/ is empty — nothing to do")
        return

    dest = _dest_dir()

    for path in files:
        if path.name.startswith("."):
            continue
        if path.is_dir():
            continue  # e.g. intake/quarantine/
        if path.name.endswith(image_importer.SIDECAR_SUFFIX):
            continue  # Slack thread sidecar — handled alongside its main file

        suffix = path.suffix.lower()

        if suffix == ".csv":
            logger.info("watcher: importing YNAB CSV: %s", path.name)
            imported, skipped = ynab_csv.import_file(path)
            logger.info("watcher: %s → %d imported, %d skipped", path.name, imported, skipped)
            shutil.move(str(path), dest / path.name)

        elif suffix == ".pdf":
            logger.info("watcher: importing PDF: %s", path.name)
            ok = pdf_importer.import_file(path)
            if ok:
                shutil.move(str(path), dest / path.name)
            else:
                logger.info("watcher: %s already imported — moving anyway", path.name)
                shutil.move(str(path), dest / path.name)

        elif suffix in _IMAGE_EXTS:
            logger.info("watcher: importing image: %s", path.name)
            ok = image_importer.import_file(path)
            if ok:
                shutil.move(str(path), dest / path.name)
                # importer should have removed the sidecar already; clean up if not
                sc = path.with_name(path.name + image_importer.SIDECAR_SUFFIX)
                if sc.exists():
                    try:
                        sc.unlink()
                    except OSError:
                        pass
            else:
                attempts = image_importer.get_attempts(path)
                if attempts >= image_importer.MAX_OCR_ATTEMPTS:
                    image_importer.quarantine(path)
                else:
                    logger.warning(
                        "watcher: image import failed for %s (attempt %d/%d) — leaving in intake/",
                        path.name, attempts, image_importer.MAX_OCR_ATTEMPTS,
                    )

        else:
            logger.warning("watcher: unrecognised file type %s — skipping", path.name)
