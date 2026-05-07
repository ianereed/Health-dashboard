"""Phase 16 Chunk 2 — tests for meal_planner_photo_intake_scan kind."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import jobs.kinds.meal_planner_photo_intake_scan as scan_mod
from meal_planner.db import _SCHEMA, _get_conn


def _fake_jpg(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _setup(tmp_path: Path, monkeypatch, enqueue_mock: MagicMock):
    """Wire up a tmp intake_dir + tmp DB and return (intake_dir, db_path)."""
    import jobs.lib
    import meal_planner.vision.intake_db as idb

    intake_dir = tmp_path / "photo-intake"
    intake_dir.mkdir()
    db_p = tmp_path / "recipes.db"
    with _get_conn(db_p) as c:
        c.executescript(_SCHEMA)

    monkeypatch.setattr(idb, "DB_PATH", db_p)
    monkeypatch.setenv("MEAL_PLANNER_NAS_INTAKE_DIR", str(intake_dir))
    monkeypatch.setattr(jobs.lib.RequiresSpec, "validate", lambda self: [])
    # Prevent the real ingest task from running during scan tests.
    monkeypatch.setattr(scan_mod, "meal_planner_ingest_photo", enqueue_mock)
    return intake_dir, db_p


def test_scan_discovers_and_enqueues(tmp_path, monkeypatch):
    """Two JPGs in drop zone → both renamed to _processing/, both DB rows, both enqueues."""
    enqueue_mock = MagicMock()
    intake_dir, db_p = _setup(tmp_path, monkeypatch, enqueue_mock)

    _fake_jpg(intake_dir / "IMG_001.jpg", b"\xff\xd8\xff\xe0" + b"\x01" * 100)
    _fake_jpg(intake_dir / "IMG_002.jpg", b"\xff\xd8\xff\xe0" + b"\x02" * 100)

    result = scan_mod.meal_planner_photo_intake_scan.func()

    assert result["discovered"] == 2
    assert result["enqueued"] == 2
    assert result["skipped_dup"] == 0

    # Subfolders created
    for sub in ("_processing", "_done", "_skipped", "_wedged"):
        assert (intake_dir / sub).is_dir()

    # Source files gone from drop zone root
    assert not (intake_dir / "IMG_001.jpg").exists()
    assert not (intake_dir / "IMG_002.jpg").exists()

    # Files now in _processing/ with sha names
    processing = list((intake_dir / "_processing").iterdir())
    assert len(processing) == 2
    assert all(f.suffix == ".jpg" for f in processing)

    # DB rows exist at status=pending
    from meal_planner.vision.intake_db import list_pending
    pending = list_pending(db_path=db_p)
    assert len(pending) == 2

    # Enqueue called once per photo with the sha
    assert enqueue_mock.call_count == 2
    enqueued_shas = {call.args[0] for call in enqueue_mock.call_args_list}
    db_shas = {r.sha for r in pending}
    assert enqueued_shas == db_shas


def test_scan_dedup_no_op(tmp_path, monkeypatch):
    """Re-dropping content with the same SHA is a complete no-op on the second scan."""
    enqueue_mock = MagicMock()
    intake_dir, db_p = _setup(tmp_path, monkeypatch, enqueue_mock)

    # First scan
    _fake_jpg(intake_dir / "IMG_003.jpg", b"\xff\xd8\xff\xe0" + b"\x03" * 100)
    result1 = scan_mod.meal_planner_photo_intake_scan.func()
    assert result1["enqueued"] == 1

    # Drop same content again under a different filename
    _fake_jpg(intake_dir / "IMG_003_dup.jpg", b"\xff\xd8\xff\xe0" + b"\x03" * 100)
    result2 = scan_mod.meal_planner_photo_intake_scan.func()

    assert result2["discovered"] == 1
    assert result2["enqueued"] == 0
    assert result2["skipped_dup"] == 1
    assert enqueue_mock.call_count == 1  # only the original enqueue

    # Still only one DB row
    from meal_planner.vision.intake_db import list_pending
    rows = list_pending(db_path=db_p)
    assert len(rows) == 1


def test_scan_os_error_exits_cleanly(tmp_path, monkeypatch):
    """OSError from iterdir (NAS unmounted) → returns discovered=0 without raising."""
    import jobs.lib
    import meal_planner.vision.intake_db as idb
    db_p = tmp_path / "recipes.db"
    with _get_conn(db_p) as c:
        c.executescript(_SCHEMA)

    monkeypatch.setattr(idb, "DB_PATH", db_p)
    monkeypatch.setenv("MEAL_PLANNER_NAS_INTAKE_DIR", str(tmp_path / "does_not_exist"))
    monkeypatch.setattr(jobs.lib.RequiresSpec, "validate", lambda self: [])
    monkeypatch.setattr(scan_mod, "meal_planner_ingest_photo", MagicMock())

    result = scan_mod.meal_planner_photo_intake_scan.func()
    assert result["discovered"] == 0
    assert result["enqueued"] == 0
    assert "tick_at" in result


def test_scan_ignores_non_image_files(tmp_path, monkeypatch):
    """Non-image files (txt, md) in drop zone are skipped; only JPG counts."""
    enqueue_mock = MagicMock()
    intake_dir, db_p = _setup(tmp_path, monkeypatch, enqueue_mock)

    (intake_dir / "notes.txt").write_text("not an image")
    (intake_dir / "README.md").write_text("also not an image")
    _fake_jpg(intake_dir / "real.jpg", b"\xff\xd8\xff\xe0" + b"\x04" * 100)

    result = scan_mod.meal_planner_photo_intake_scan.func()

    assert result["discovered"] == 1
    assert result["enqueued"] == 1
    assert enqueue_mock.call_count == 1
