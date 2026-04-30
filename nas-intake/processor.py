"""Per-file pipeline: subprocess to event-aggregator ingest-image, parent-rooted filing, archive source, journal append.

For each candidate file in an intake/ folder:
  1. SHA256 dedup check
  2. Subprocess `event-aggregator/main.py ingest-image --file <path>` with NAS_WRITE_DISABLED=1
  3. Read _metadata.json from event-aggregator/staging/local_<sha>/
  4. Build parent-rooted destination: <parent>/<year>/<doc-type>/<date>_<slug>[-N]/
  5. Copy staged dir contents (page renderings + extraction artifacts) + the original
  6. Move source: intake/<file> → intake/_processed/<YYYY-MM>/<file>
  7. Purge event-aggregator's staging dir
  8. Append journal entry on parent

Errors leave source in intake/ — next tick retries. v1 has no quarantine counter.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger(__name__)


# ── doc-type → folder name (verbatim from event-aggregator/writers/file_writer.py) ──

_DOC_TYPE_FOLDER = {
    "medical_portal_screenshot": "Portal-Screenshots",
    "medical_form": "Forms",
    "insurance_eob": "Insurance-EOB",
    "insurance_document": "Insurance",
    "prescription": "Prescriptions",
    "lab_results": "Lab-Results",
    "receipt": "Receipts",
    "invoice": "Invoices",
    "tax_form": "Tax-Documents",
    "bank_statement": "Bank-Statements",
    "contract": "Contracts",
    "id_card": "ID-Cards",
    "recipe": "Recipes",
    "photo": "Photos",
    "home_improvement": "Projects",
    "mortgage_document": "Mortgage",
    "utility_bill": "Utilities",
}


def _doc_type_to_folder(doc_type: str) -> str:
    if not doc_type:
        return "General"
    mapped = _DOC_TYPE_FOLDER.get(doc_type.lower().strip())
    if mapped:
        return mapped
    return "-".join(word.capitalize() for word in doc_type.replace("_", " ").split()) or "General"


def _slugify(text: str, max_len: int = 60) -> str:
    slug = (text or "").lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug).strip("-")
    return slug[:max_len] or "untitled"


# ── result type ─────────────────────────────────────────────────────────

@dataclass
class ProcessResult:
    ok: bool
    reason: str = ""
    filed_path: Path | None = None
    journal_entry: dict | None = None


# ── pipeline ────────────────────────────────────────────────────────────

def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_dest(parent: Path, meta: dict) -> Path:
    """parent / <year> / <doc-type-folder> / <date>_<slug>[-N]/"""
    date_str = (meta.get("date") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    year = date_str[:4]
    doc_type_folder = _doc_type_to_folder(meta.get("document_type", ""))
    slug = _slugify(meta.get("title") or "untitled")
    base = parent / year / doc_type_folder
    candidate = base / f"{date_str}_{slug}"
    if not candidate.exists():
        return candidate
    for i in range(2, 100):
        c = base / f"{date_str}_{slug}-{i}"
        if not c.exists():
            return c
    raise RuntimeError(f"too many path collisions under {base} for slug {slug}")


def _run_ingest_image(file: Path) -> tuple[int, str, str]:
    """Subprocess to event-aggregator's CLI with NAS_WRITE_DISABLED=1.
    Returns (returncode, stdout, stderr).
    """
    env = {**os.environ, "NAS_WRITE_DISABLED": "1"}
    cmd = [str(config.EA_VENV_PYTHON), "main.py", "ingest-image", "--file", str(file)]
    logger.info("processor: invoking %s (env NAS_WRITE_DISABLED=1)", " ".join(cmd))
    try:
        r = subprocess.run(
            cmd, cwd=str(config.EVENT_AGGREGATOR_ROOT),
            env=env, capture_output=True, text=True,
            timeout=config.SUBPROCESS_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return (-1, "", f"subprocess timed out after {config.SUBPROCESS_TIMEOUT_S}s")
    return (r.returncode, r.stdout or "", r.stderr or "")


def _find_staged_dir(file_sha: str) -> Path | None:
    """ingest-image stages files at event-aggregator/staging/local_<sha12>/.
    sha12 is the first 12 chars of file_bytes' SHA256 (see image_pipeline.py:82).
    """
    expected = config.EVENT_AGGREGATOR_ROOT / "staging" / f"local_{file_sha[:12]}"
    return expected if expected.exists() else None


def _copy_staged_to_dest(staged: Path, source: Path, dest: Path) -> None:
    """Copy contents of staged/ to dest/, plus the original source file.
    Skips _metadata.json (internal metadata, not for the destination)."""
    dest.mkdir(parents=True, exist_ok=True)
    for item in staged.iterdir():
        if item.name == "_metadata.json":
            continue
        shutil.copy2(str(item), str(dest / item.name))
    # Also copy the original source file (staging only has rasterized pages
    # + extraction artifacts, not the source PDF/image itself).
    shutil.copy2(str(source), str(dest / source.name))


def _archive_source(source: Path, intake_dir: Path) -> Path:
    """Move source → intake/_processed/YYYY-MM/<file>."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    archive = intake_dir / "_processed" / month
    archive.mkdir(parents=True, exist_ok=True)
    target = archive / source.name
    # If a same-named file is already there (rare; deduplicated above), suffix it.
    if target.exists():
        for i in range(2, 100):
            c = archive / f"{source.stem}-{i}{source.suffix}"
            if not c.exists():
                target = c
                break
    shutil.move(str(source), str(target))
    return target


def _purge_staged(staged: Path) -> None:
    try:
        shutil.rmtree(staged)
    except OSError as exc:
        logger.warning("processor: failed to purge staging %s: %s", staged, exc)


def process_one(file: Path, parent: Path, intake_dir: Path, file_sha: str) -> ProcessResult:
    """Run the full pipeline on one file. Returns ProcessResult.
    Caller is responsible for filtering (extension, dedup, stability gate)
    BEFORE calling this — process_one assumes it should run.
    """
    logger.info("processor: processing %s under parent %s", file.name, parent)

    rc, stdout, stderr = _run_ingest_image(file)
    if rc != 0:
        return ProcessResult(False, f"ingest-image rc={rc}; stderr={stderr.strip()[:300]}")

    staged = _find_staged_dir(file_sha)
    if staged is None:
        return ProcessResult(False, f"staged dir not found at staging/local_{file_sha[:12]}")

    meta_path = staged / "_metadata.json"
    if not meta_path.exists():
        return ProcessResult(False, f"_metadata.json missing in {staged}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return ProcessResult(False, f"bad metadata: {exc}")

    try:
        dest = _build_dest(parent, meta)
    except Exception as exc:
        return ProcessResult(False, f"build_dest failed: {exc}")

    try:
        _copy_staged_to_dest(staged, file, dest)
    except Exception as exc:
        return ProcessResult(False, f"copy to NAS failed: {exc}")

    try:
        archived = _archive_source(file, intake_dir)
    except Exception as exc:
        # Files copied to NAS but source not moved — log and surface so user
        # can manually clear. Don't roll back the NAS copy (it's already there).
        return ProcessResult(False, f"archive source failed (file copied to NAS at {dest}): {exc}")

    _purge_staged(staged)

    rel = dest.relative_to(parent) if dest.is_relative_to(parent) else dest
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "filed_path": str(dest),
        "filed_rel": str(rel),
        "source_name": file.name,
        "title": meta.get("title", ""),
        "doc_date": meta.get("date", ""),
        "doc_type": meta.get("document_type", ""),
        "category": meta.get("primary_category", ""),
        "subcategory": meta.get("subcategory", ""),
        "confidence": meta.get("confidence", 0.0) if isinstance(meta.get("confidence"), (int, float)) else 0.0,
        "summary": meta.get("summary", ""),
        "sha256": file_sha,
        "archived_to": str(archived),
    }
    return ProcessResult(True, "", filed_path=dest, journal_entry=entry)
