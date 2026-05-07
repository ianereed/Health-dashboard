"""T8 — validate status strings in mark_status."""
from __future__ import annotations

from pathlib import Path

import pytest

from meal_planner.db import _SCHEMA, _get_conn
from meal_planner.vision.intake_db import get_by_sha, mark_status, record_intake


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
        assert get_by_sha(sha, db_path=db_p).status == status


def test_ok_partial_is_valid_status(tmp_path):
    db_p = _setup_db(tmp_path)
    record_intake("sha_op", "src.jpg", "/nas/sha_op.jpg", path=db_p)
    mark_status("sha_op", "ok_partial", db_path=db_p)  # must not raise
    assert get_by_sha("sha_op", db_path=db_p).status == "ok_partial"


def test_ok_partial_sets_completed_at(tmp_path):
    db_p = _setup_db(tmp_path)
    record_intake("sha_opc", "src.jpg", "/nas/sha_opc.jpg", path=db_p)
    mark_status("sha_opc", "ok_partial", db_path=db_p)
    row = get_by_sha("sha_opc", db_path=db_p)
    assert row.completed_at is not None


def test_extraction_warnings_persisted(tmp_path):
    db_p = _setup_db(tmp_path)
    record_intake("sha_ew", "src.jpg", "/nas/sha_ew.jpg", path=db_p)
    mark_status("sha_ew", "ok_partial", extraction_warnings='["row 0: foo"]', db_path=db_p)
    row = get_by_sha("sha_ew", db_path=db_p)
    assert row.extraction_warnings == '["row 0: foo"]'


def test_extraction_warnings_default_none_preserves_existing(tmp_path):
    db_p = _setup_db(tmp_path)
    record_intake("sha_ewp", "src.jpg", "/nas/sha_ewp.jpg", path=db_p)
    mark_status("sha_ewp", "ok_partial", extraction_warnings='["row 0: bar"]', db_path=db_p)
    # Call again without extraction_warnings — COALESCE must preserve the existing value
    mark_status("sha_ewp", "extracting", db_path=db_p)
    row = get_by_sha("sha_ewp", db_path=db_p)
    assert row.extraction_warnings == '["row 0: bar"]'
