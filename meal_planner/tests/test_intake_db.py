"""T8 — validate status strings in mark_status."""
from __future__ import annotations

from pathlib import Path

import pytest

from meal_planner.db import _SCHEMA, _get_conn
from meal_planner.vision.intake_db import mark_status, record_intake


def _setup_db(tmp_path: Path) -> Path:
    db_p = tmp_path / "recipes.db"
    with _get_conn(db_p) as c:
        c.executescript(_SCHEMA)
    return db_p


def test_intake_db_rejects_unknown_status(tmp_path):
    db_p = _setup_db(tmp_path)
    record_intake("abc123", "src.jpg", "/nas/abc123.jpg", path=db_p)

    with pytest.raises(ValueError, match="unknown status"):
        mark_status("abc123", "oklay", db_path=db_p)


def test_intake_db_accepts_all_valid_statuses(tmp_path):
    """Sanity check that every status in _VALID_STATUSES is accepted."""
    from meal_planner.vision.intake_db import _VALID_STATUSES

    db_p = _setup_db(tmp_path)
    for i, status in enumerate(_VALID_STATUSES):
        sha = f"sha{i:04d}"
        record_intake(sha, f"{sha}.jpg", f"/nas/{sha}.jpg", path=db_p)
        mark_status(sha, status, db_path=db_p)  # must not raise
