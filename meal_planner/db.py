from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_DIR = Path.home() / "Home-Tools" / "meal_planner"
DB_PATH = DB_DIR / "recipes.db"

_PRAGMAS = (
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("busy_timeout", "5000"),
    ("foreign_keys", "ON"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    base_servings INTEGER NOT NULL DEFAULT 4,
    instructions TEXT,
    cook_time_min INTEGER,
    source TEXT,
    photo_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingredients (
    id INTEGER PRIMARY KEY,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    qty_per_serving REAL,
    unit TEXT,
    notes TEXT,
    todoist_section TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL DEFAULT 'user'
);
CREATE TABLE IF NOT EXISTS recipe_tags (
    recipe_id INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (recipe_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_recipes_title ON recipes(title);
CREATE INDEX IF NOT EXISTS idx_ingredients_recipe ON ingredients(recipe_id);
"""


def _get_conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    for key, val in _PRAGMAS:
        conn.execute(f"PRAGMA {key}={val}")
    return conn


def init_db(path: Path | str | None = None) -> None:
    """Apply schema + pragmas. Idempotent — safe to call multiple times."""
    p = Path(path) if path is not None else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with _get_conn(p) as conn:
        conn.executescript(_SCHEMA)


def insert_recipe(
    *,
    title: str,
    base_servings: int = 4,
    instructions: str | None = None,
    cook_time_min: int | None = None,
    source: str | None = None,
    photo_path: str | None = None,
    path: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Insert a recipe row and return its new id.

    When conn is passed, uses it without committing or closing (caller owns the
    transaction). When conn is None, opens and commits its own connection.
    """
    now = datetime.now(timezone.utc).isoformat()
    sql = """
        INSERT INTO recipes
          (title, base_servings, instructions, cook_time_min,
           source, photo_path, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
    params = (title, base_servings, instructions, cook_time_min,
              source, photo_path, now, now)
    if conn is not None:
        cur = conn.execute(sql, params)
        return cur.lastrowid  # type: ignore[return-value]
    p = path or DB_PATH
    with _get_conn(p) as c:
        cur = c.execute(sql, params)
        return cur.lastrowid  # type: ignore[return-value]


def insert_ingredient(
    *,
    recipe_id: int,
    name: str,
    qty_per_serving: float | None = None,
    unit: str | None = None,
    notes: str | None = None,
    todoist_section: str | None = None,
    sort_order: int = 0,
    path: Path | None = None,
) -> int:
    p = path or DB_PATH
    with _get_conn(p) as conn:
        cur = conn.execute(
            """
            INSERT INTO ingredients
              (recipe_id, name, qty_per_serving, unit, notes,
               todoist_section, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (recipe_id, name, qty_per_serving, unit, notes,
             todoist_section, sort_order),
        )
        return cur.lastrowid  # type: ignore[return-value]


def add_recipe_tag(
    recipe_id: int,
    tag: str,
    *,
    path: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Insert tag if new, then link to the recipe. Idempotent.

    Tag names are case-folded to lowercase on write; queries do not need to fold.
    When conn is passed, uses it without committing or closing (caller owns the
    transaction). When conn is None, opens and commits its own connection.
    """
    tag = tag.strip().lower()
    def _run(c: sqlite3.Connection) -> None:
        c.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
        c.execute(
            """
            INSERT OR IGNORE INTO recipe_tags (recipe_id, tag_id)
            SELECT ?, id FROM tags WHERE name = ?
            """,
            (recipe_id, tag),
        )
    if conn is not None:
        _run(conn)
        return
    p = path or DB_PATH
    with _get_conn(p) as c:
        _run(c)


# ---------------------------------------------------------------------------
# Migration runner stub — no migrations yet in V0
# ---------------------------------------------------------------------------

def run_migrations(path: Path | None = None) -> None:
    """Apply pending schema migrations (none in V0)."""
