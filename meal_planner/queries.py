from __future__ import annotations

from pathlib import Path

from meal_planner import db as _db
from meal_planner.models import Recipe


def _row_to_recipe(row) -> Recipe:
    return Recipe(
        id=row["id"],
        title=row["title"],
        base_servings=row["base_servings"],
        instructions=row["instructions"],
        cook_time_min=row["cook_time_min"],
        source=row["source"],
        photo_path=row["photo_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_recipes(
    *, tag: str | None = None, path: Path | None = None
) -> list[Recipe]:
    """Return all recipes ordered by title, optionally filtered to a single tag."""
    p = path or _db.DB_PATH
    with _db._get_conn(p) as conn:
        if tag is None:
            rows = conn.execute(
                "SELECT * FROM recipes ORDER BY title COLLATE NOCASE"
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT r.* FROM recipes r
                JOIN recipe_tags rt ON rt.recipe_id = r.id
                JOIN tags t ON t.id = rt.tag_id
                WHERE t.name = ?
                ORDER BY r.title COLLATE NOCASE
                """,
                (tag,),
            ).fetchall()
    return [_row_to_recipe(r) for r in rows]


def get_recipe(recipe_id: int, *, path: Path | None = None) -> Recipe:
    """Return the recipe with the given id.

    Raises KeyError if no matching recipe exists.
    """
    p = path or _db.DB_PATH
    with _db._get_conn(p) as conn:
        row = conn.execute(
            "SELECT * FROM recipes WHERE id = ?", (recipe_id,)
        ).fetchone()
    if row is None:
        raise KeyError(recipe_id)
    return _row_to_recipe(row)


def search_recipes(
    *,
    name_substring: str = "",
    tags: tuple[str, ...] = (),
    path: Path | None = None,
) -> list[Recipe]:
    """Return recipes matching name_substring AND all given tags, ordered by title.

    name_substring is a case-insensitive LIKE match on the title.
    tags filters to recipes that have ALL listed tags.
    Both filters are AND-combined; empty values mean "no filter on that axis".
    """
    tags = tuple(dict.fromkeys(tags))  # dedupe while preserving order
    p = path or _db.DB_PATH
    with _db._get_conn(p) as conn:
        if tags:
            placeholders = ",".join("?" * len(tags))
            rows = conn.execute(
                f"""
                SELECT r.* FROM recipes r
                WHERE lower(r.title) LIKE lower(?)
                  AND (
                    SELECT COUNT(DISTINCT t.name)
                    FROM recipe_tags rt
                    JOIN tags t ON t.id = rt.tag_id
                    WHERE rt.recipe_id = r.id AND t.name IN ({placeholders})
                  ) = ?
                ORDER BY r.title COLLATE NOCASE
                """,
                (f"%{name_substring}%", *tags, len(tags)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM recipes WHERE lower(title) LIKE lower(?) ORDER BY title COLLATE NOCASE",
                (f"%{name_substring}%",),
            ).fetchall()
    return [_row_to_recipe(r) for r in rows]
