import sqlite3
import tempfile
from pathlib import Path

import pytest

from meal_planner.db import _get_conn, init_db, insert_recipe, insert_ingredient, add_recipe_tag


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "recipes.db"
    init_db(p)
    return p


def test_schema_applies(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"recipes", "ingredients", "tags", "recipe_tags"}.issubset(tables)
    conn.close()


def test_wal_pragma(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    conn.close()


def test_foreign_keys_on(db_path: Path) -> None:
    # foreign_keys is per-connection; verify _get_conn applies it
    with _get_conn(db_path) as conn:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1


def test_idempotent_reinit(tmp_path: Path) -> None:
    p = tmp_path / "recipes.db"
    init_db(p)
    init_db(p)  # second call must not raise or corrupt
    conn = sqlite3.connect(str(p))
    count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
    assert count == 0
    conn.close()


def test_insert_recipe_returns_id(db_path: Path) -> None:
    rid = insert_recipe(title="Test Soup", base_servings=2, path=db_path)
    assert isinstance(rid, int)
    assert rid > 0


def test_insert_ingredient(db_path: Path) -> None:
    rid = insert_recipe(title="Test Soup", base_servings=2, path=db_path)
    iid = insert_ingredient(
        recipe_id=rid, name="water", qty_per_serving=2.0, unit="cup", path=db_path
    )
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT name, qty_per_serving, unit FROM ingredients WHERE id = ?", (iid,)
    ).fetchone()
    assert row == ("water", 2.0, "cup")
    conn.close()


def test_add_recipe_tag_idempotent(db_path: Path) -> None:
    rid = insert_recipe(title="Test Soup", base_servings=2, path=db_path)
    add_recipe_tag(rid, "asian", path=db_path)
    add_recipe_tag(rid, "asian", path=db_path)  # must not raise or duplicate
    conn = sqlite3.connect(str(db_path))
    count = conn.execute(
        "SELECT COUNT(*) FROM recipe_tags WHERE recipe_id = ?", (rid,)
    ).fetchone()[0]
    assert count == 1
    conn.close()


def test_cascade_delete(db_path: Path) -> None:
    rid = insert_recipe(title="Cascade Test", base_servings=4, path=db_path)
    insert_ingredient(recipe_id=rid, name="salt", path=db_path)
    add_recipe_tag(rid, "simple", path=db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("DELETE FROM recipes WHERE id = ?", (rid,))
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM ingredients WHERE recipe_id = ?", (rid,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM recipe_tags WHERE recipe_id = ?", (rid,)
    ).fetchone()[0] == 0
    conn.close()
