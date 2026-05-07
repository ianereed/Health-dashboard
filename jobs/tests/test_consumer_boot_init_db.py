"""T1 — verify _init_meal_planner_schema() creates photos_intake at consumer boot.

conftest.py sets HOME → tmp before `from jobs import huey`, which fires
_init_meal_planner_schema() → init_db(). This test just asserts the side effect
is visible: the recipes.db exists and contains the photos_intake table.
"""
from __future__ import annotations

import sqlite3


def test_photos_intake_table_exists_after_boot():
    from meal_planner.db import DB_PATH

    assert DB_PATH.exists(), f"recipes.db not created at boot: {DB_PATH}"

    conn = sqlite3.connect(str(DB_PATH))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    conn.close()

    assert "photos_intake" in tables, f"photos_intake table missing; found: {tables}"
