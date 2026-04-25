"""
File router — maps a classified file to its destination project or staging
subdir.

Routing rules (see /Users/ianreed/.claude/plans/we-are-going-to-ancient-platypus.md):
  Financial          → finance-monitor/intake/
  Healthcare         → nas-staging/Healthcare/<subcategory or 'unsorted'>/
  Recipes            → nas-staging/Recipes/
  Documents/Identification/Engineering/Books/Wedding/DIY Projects/334_Iris
                     → nas-staging/<category>/<year>/
  Events (detected)  → handled separately by ingest_as_event()
  confidence < 0.3   → nas-staging/Unsorted/ (caller decides override)
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import config
from classifier import Classification

logger = logging.getLogger(__name__)

# Categories that route into finance-monitor's intake/ dir rather than NAS staging.
_FINANCE_CATEGORIES = frozenset({"Financial"})

# All known NAS-only categories that stage under NAS_STAGING_DIR/<category>/.
_NAS_CATEGORIES = frozenset({
    "Healthcare", "Documents", "Engineering", "Identification",
    "Recipes", "334_Iris", "Wedding", "Books", "DIY Projects",
})

# Any category the classifier might emit that we don't know about lands here.
_FALLBACK_CATEGORY = "Documents"

# When confidence is below this, route to Unsorted/ regardless of category.
LOW_CONFIDENCE_THRESHOLD = 0.3


@dataclass
class RouteResult:
    destination: Path          # absolute final path of the file
    project: str               # "finance-monitor", "nas-staging", or "event-aggregator"
    category: str              # the logical bucket used for display/override
    was_low_confidence: bool   # True if confidence forced Unsorted
    override_used: str | None = None  # category name if !route was used


def route(
    src_file: Path,
    classification: Classification,
    override: str | None = None,
) -> RouteResult:
    """Move the source file to its routing destination.

    Args:
        src_file: file currently sitting in tmp/
        classification: result from classifier.classify()
        override: if set, treat this as the category (bypass classifier result)
    """
    category = (override or classification.category or _FALLBACK_CATEGORY).strip()

    was_low_confidence = (
        override is None
        and classification.confidence < LOW_CONFIDENCE_THRESHOLD
    )
    if was_low_confidence:
        category = "Unsorted"

    if category in _FINANCE_CATEGORIES:
        dest = _finance_dest(src_file, classification)
        project = "finance-monitor"
    elif category == "Unsorted":
        dest = config.NAS_STAGING_DIR / "Unsorted" / _safe_filename(src_file, classification)
        project = "nas-staging"
    elif category in _NAS_CATEGORIES or override:
        dest = _nas_dest(src_file, classification, category)
        project = "nas-staging"
    else:
        dest = _nas_dest(src_file, classification, _FALLBACK_CATEGORY)
        project = "nas-staging"

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_file), str(dest))
    logger.info("router: %s → %s (category=%s, project=%s)", src_file.name, dest, category, project)

    return RouteResult(
        destination=dest,
        project=project,
        category=category,
        was_low_confidence=was_low_confidence,
        override_used=override,
    )


def ingest_as_event(src_file: Path) -> tuple[bool, str]:
    """For Events-classified files, hand off to event-aggregator's ingest-image CLI.

    Returns (ok, message). The CLI is expected to do its own classification,
    calendar extraction, and proposal posting to ian-event-aggregator.
    """
    python = config.EVENT_AGGREGATOR_PYTHON
    main_py = config.EVENT_AGGREGATOR_DIR / "main.py"

    if not Path(python).exists():
        return False, f"event-aggregator python not found at {python}"
    if not main_py.exists():
        return False, f"event-aggregator main.py not found at {main_py}"

    try:
        result = subprocess.run(
            [python, str(main_py), "ingest-image", "--file", str(src_file)],
            cwd=str(config.EVENT_AGGREGATOR_DIR),
            capture_output=True,
            text=True,
            timeout=240,
        )
    except subprocess.TimeoutExpired:
        return False, "ingest-image timed out after 240s"

    if result.returncode != 0:
        tail = "\n".join((result.stderr or "").splitlines()[-10:])
        return False, f"ingest-image exited {result.returncode}:\n{tail}"

    return True, (result.stdout.strip() or "ingested")


def _finance_dest(src: Path, cls: Classification) -> Path:
    """Drop into finance-monitor/intake/ with a timestamped prefix so two
    uploads with the same name don't collide."""
    config.FINANCE_MONITOR_INTAKE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = _safe_filename(src, cls)
    return config.FINANCE_MONITOR_INTAKE / f"{stamp}_{filename}"


def _nas_dest(src: Path, cls: Classification, category: str) -> Path:
    """Build the nas-staging/<category>/<year>/<filename> path."""
    year = (cls.date or "")[:4]
    if not year or not year.isdigit():
        year = datetime.now().strftime("%Y")
    sub = cls.subcategory or ""
    parts: list[str] = [category]
    if sub:
        parts.append(_slugify(sub))
    parts.append(year)
    base = config.NAS_STAGING_DIR
    for p in parts:
        base = base / p
    return base / _safe_filename(src, cls)


def _safe_filename(src: Path, cls: Classification) -> str:
    """Return an on-disk filename based on the classifier's title if present,
    else the upload's original name."""
    if cls.title:
        stem = _slugify(cls.title)[:80]
        return f"{stem}{src.suffix}" if src.suffix else stem
    return src.name


def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "untitled"
