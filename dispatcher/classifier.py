"""
Local document classifier — thin wrapper around event-aggregator's
image_analyzer. Shells out to a CLI subcommand so the dispatcher doesn't
import event-aggregator's Python package (keeps the two projects decoupled).

All model calls stay on-device (qwen2.5vl:7b via Ollama). No cloud fallback.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import config

logger = logging.getLogger(__name__)


@dataclass
class Classification:
    category: str          # top-level NAS folder, e.g. "Financial", "Healthcare"
    subcategory: str | None  # e.g. "0-Ian Healthcare", or None
    doc_type: str          # e.g. "statement", "invoice", "save_the_date"
    confidence: float      # 0.0–1.0
    title: str             # short descriptive title from the model
    date: str | None       # YYYY-MM-DD if the doc has one, else None
    error: str | None = None

    @property
    def routing_category(self) -> str:
        """Return the canonical routing key used by router.py."""
        return self.category or "Documents"


def classify(file_path: Path) -> Classification:
    """Run event-aggregator's local classifier on a single file.

    Never raises; on any failure, returns a Classification with `error` set
    and `confidence=0.0` so the router falls through to Unsorted.
    """
    python = config.EVENT_AGGREGATOR_PYTHON
    main_py = config.EVENT_AGGREGATOR_DIR / "main.py"

    if not Path(python).exists():
        return _error(f"event-aggregator python not found at {python}")
    if not main_py.exists():
        return _error(f"event-aggregator main.py not found at {main_py}")

    try:
        result = subprocess.run(
            [python, str(main_py), "classify", "--file", str(file_path)],
            cwd=str(config.EVENT_AGGREGATOR_DIR),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return _error(f"classify timed out after 180s for {file_path.name}")
    except Exception as exc:
        return _error(f"classify subprocess failed: {exc}")

    if result.returncode != 0:
        stderr_tail = (result.stderr or "").splitlines()[-5:]
        return _error(
            f"classify exited {result.returncode}: {' | '.join(stderr_tail)}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return _error(f"classify returned non-JSON: {exc}")

    return Classification(
        category=data.get("category", "Documents"),
        subcategory=data.get("subcategory"),
        doc_type=data.get("doc_type", ""),
        confidence=float(data.get("confidence", 0.0)),
        title=data.get("title", file_path.name),
        date=data.get("date"),
    )


def _error(msg: str) -> Classification:
    logger.warning("classifier: %s", msg)
    return Classification(
        category="Documents",
        subcategory=None,
        doc_type="",
        confidence=0.0,
        title="",
        date=None,
        error=msg,
    )
