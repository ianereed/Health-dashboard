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


def test_add_recipe_tag_case_folding(db_path: Path) -> None:
    rid = insert_recipe(title="Tag Case Test", base_servings=4, path=db_path)
    add_recipe_tag(rid, "Asian", path=db_path)
    add_recipe_tag(rid, "asian", path=db_path)  # same after fold — must not duplicate
    conn = sqlite3.connect(str(db_path))
    tag_count = conn.execute("SELECT COUNT(*) FROM tags WHERE name = 'asian'").fetchone()[0]
    link_count = conn.execute(
        "SELECT COUNT(*) FROM recipe_tags WHERE recipe_id = ?", (rid,)
    ).fetchone()[0]
    conn.close()
    assert tag_count == 1
    assert link_count == 1


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


def test_insert_recipe_external_conn_not_visible_until_commit(db_path: Path) -> None:
    """insert_recipe with conn= must not be visible on other connections before commit."""
    conn = _get_conn(db_path)
    try:
        insert_recipe(title="Isolation Test", base_servings=4, conn=conn)
        # Fresh independent connection — should see nothing yet
        check = sqlite3.connect(str(db_path))
        count = check.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
        check.close()
        assert count == 0, "uncommitted write leaked to another connection"
        conn.commit()
        check = sqlite3.connect(str(db_path))
        count = check.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
        check.close()
        assert count == 1
    finally:
        conn.close()


def test_add_recipe_tag_external_conn_not_visible_until_commit(db_path: Path) -> None:
    """add_recipe_tag with conn= must not be visible on other connections before commit."""
    rid = insert_recipe(title="Tag Isolation", base_servings=4, path=db_path)
    conn = _get_conn(db_path)
    try:
        add_recipe_tag(rid, "italian", conn=conn)
        check = sqlite3.connect(str(db_path))
        count = check.execute("SELECT COUNT(*) FROM tags WHERE name = 'italian'").fetchone()[0]
        check.close()
        assert count == 0, "uncommitted tag write leaked to another connection"
        conn.commit()
        check = sqlite3.connect(str(db_path))
        count = check.execute("SELECT COUNT(*) FROM tags WHERE name = 'italian'").fetchone()[0]
        check.close()
        assert count == 1
    finally:
        conn.close()
