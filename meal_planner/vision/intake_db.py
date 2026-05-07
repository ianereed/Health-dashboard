"""photos_intake table operations.

The table itself is created by meal_planner.db.init_db (Phase 16 schema add).
This module provides typed CRUD for the worker code in Chunks 2-4.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from meal_planner.db import DB_PATH, _get_conn, init_db

_VALID_STATUSES = frozenset({
    "pending", "extracting", "ok",
    "parse_fail", "validation_fail", "ollama_error", "timeout",
    "outlier_pending", "gemini_pending", "gemini_ok",
    "skipped", "wedged",
})


@dataclass
class IntakeRow:
    sha: str
    source_path: str
    nas_path: str
    status: str
    recipe_id: int | None
    error: str | None
    n_retries: int
    enqueued_at: str
    completed_at: str | None
    extraction_path: str | None


def _row_to_intake(row: sqlite3.Row) -> IntakeRow:
    return IntakeRow(
        sha=row["sha"],
        source_path=row["source_path"],
        nas_path=row["nas_path"],
        status=row["status"],
        recipe_id=row["recipe_id"],
        error=row["error"],
        n_retries=row["n_retries"],
        enqueued_at=row["enqueued_at"],
        completed_at=row["completed_at"],
        extraction_path=row["extraction_path"],
    )


def init_intake_table(conn: sqlite3.Connection | None = None) -> None:
    """Ensure the photos_intake table exists. Delegates to meal_planner.db.init_db
    when conn is None; otherwise issues the schema directly on the given conn."""
    if conn is None:
        init_db()
        return
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS photos_intake (
            sha TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            nas_path TEXT NOT NULL,
            status TEXT NOT NULL,
            recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
            error TEXT,
            n_retries INTEGER NOT NULL DEFAULT 0,
            enqueued_at TEXT NOT NULL,
            completed_at TEXT,
            extraction_path TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_photos_intake_status ON photos_intake(status);
        """
    )


def record_intake(
    sha: str,
    source_path: str,
    nas_path: str,
    *,
    conn: sqlite3.Connection | None = None,
    path: Path | None = None,
) -> bool:
    """Insert a fresh pending row for a content-hash. Returns False if sha already exists."""
    now = datetime.now(timezone.utc).isoformat()
    sql = """
        INSERT OR IGNORE INTO photos_intake
          (sha, source_path, nas_path, status, n_retries, enqueued_at)
        VALUES (?, ?, ?, 'pending', 0, ?)
    """
    params = (sha, source_path, nas_path, now)
    if conn is not None:
        cur = conn.execute(sql, params)
        return cur.rowcount > 0
    p = path or DB_PATH
    with _get_conn(p) as c:
        cur = c.execute(sql, params)
        return cur.rowcount > 0


def _delete_by_sha(sha: str, *, db_path: Path | None = None) -> None:
    """Internal: remove a row when a scan-side rename failed before the file moved.

    Not for general use — Chunk 4 wedge logic owns the legitimate "remove
    photos_intake row" cases.
    """
    p = db_path or DB_PATH
    with _get_conn(p) as c:
        c.execute("DELETE FROM photos_intake WHERE sha = ?", (sha,))


def mark_status(
    sha: str,
    status: str,
    *,
    recipe_id: int | None = None,
    error: str | None = None,
    extraction_path: str | None = None,
    conn: sqlite3.Connection | None = None,
    db_path: Path | None = None,
) -> None:
    """Update status (and optionally recipe_id/error/extraction_path) for a sha row.

    Sets completed_at when the new status is a terminal one.
    """
    if status not in _VALID_STATUSES:
        raise ValueError(f"unknown status: {status!r}")
    terminal = {"ok", "skipped", "wedged", "gemini_ok"}
    completed_at = datetime.now(timezone.utc).isoformat() if status in terminal else None

    sql = """
        UPDATE photos_intake
           SET status = ?,
               recipe_id = COALESCE(?, recipe_id),
               error = ?,
               extraction_path = COALESCE(?, extraction_path),
               completed_at = COALESCE(?, completed_at)
         WHERE sha = ?
    """
    params = (status, recipe_id, error, extraction_path, completed_at, sha)
    if conn is not None:
        conn.execute(sql, params)
        return
    p = db_path or DB_PATH
    with _get_conn(p) as c:
        c.execute(sql, params)


def list_pending(
    *,
    conn: sqlite3.Connection | None = None,
    db_path: Path | None = None,
) -> list[IntakeRow]:
    """Return all rows currently at status='pending'."""
    sql = "SELECT * FROM photos_intake WHERE status = 'pending' ORDER BY enqueued_at"
    if conn is not None:
        rows = conn.execute(sql).fetchall()
        return [_row_to_intake(r) for r in rows]
    p = db_path or DB_PATH
    with _get_conn(p) as c:
        rows = c.execute(sql).fetchall()
        return [_row_to_intake(r) for r in rows]


def get_by_sha(
    sha: str,
    *,
    conn: sqlite3.Connection | None = None,
    db_path: Path | None = None,
) -> IntakeRow | None:
    sql = "SELECT * FROM photos_intake WHERE sha = ?"
    if conn is not None:
        row = conn.execute(sql, (sha,)).fetchone()
        return _row_to_intake(row) if row else None
    p = db_path or DB_PATH
    with _get_conn(p) as c:
        row = c.execute(sql, (sha,)).fetchone()
        return _row_to_intake(row) if row else None
