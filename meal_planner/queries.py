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


def list_all_tags(*, path: Path | None = None) -> list[str]:
    """Return tags linked to ≥1 recipe, sorted alphabetically.

    Tags with no recipe links are excluded so the filter UI never shows
    pills the user can't usefully click.
    """
    p = path or _db.DB_PATH
    with _db._get_conn(p) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT t.name
            FROM tags t
            JOIN recipe_tags rt ON rt.tag_id = t.id
            ORDER BY t.name
            """
        ).fetchall()
    return [r["name"] for r in rows]


def search_recipes(
    *,
    name_substring: str = "",
    tags: tuple[str, ...] = (),
    tag_logic: str = "and",
    sort: str = "alpha",
    path: Path | None = None,
) -> list[Recipe]:
    """Return recipes matching name_substring and the given tag filter.

    name_substring is a case-insensitive LIKE match on the title.
    tags filters to recipes based on tag_logic:
      "and" — recipes that have ALL listed tags (default).
      "or"  — recipes that have ANY listed tag.
    sort controls result ordering:
      "alpha"   — alphabetical by title (default; case-insensitive).
      "recent"  — most-recently-added first (id DESC).
    Both tag filters are AND-combined; empty tags means no tag filter.
    Raises ValueError for unrecognized tag_logic or sort.
    """
    if tag_logic not in ("and", "or"):
        raise ValueError(f"tag_logic must be 'and' or 'or', got {tag_logic!r}")
    # sort is validated before any SQL is composed — never reaches ORDER BY unsanitized
    if sort not in ("alpha", "recent"):
        raise ValueError(f"sort must be 'alpha' or 'recent', got {sort!r}")
    order_by = "r.title COLLATE NOCASE" if sort == "alpha" else "r.id DESC"
    tags = tuple(dict.fromkeys(tags))  # dedupe while preserving order
    p = path or _db.DB_PATH
    with _db._get_conn(p) as conn:
        if tags:
            placeholders = ",".join("?" * len(tags))
            if tag_logic == "and":
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
                    ORDER BY {order_by}
                    """,
                    (f"%{name_substring}%", *tags, len(tags)),
                ).fetchall()
            else:  # or
                rows = conn.execute(
                    f"""
                    SELECT r.* FROM recipes r
                    WHERE lower(r.title) LIKE lower(?)
                      AND EXISTS (
                        SELECT 1 FROM recipe_tags rt
                        JOIN tags t ON t.id = rt.tag_id
                        WHERE rt.recipe_id = r.id AND t.name IN ({placeholders})
                      )
                    ORDER BY {order_by}
                    """,
                    (f"%{name_substring}%", *tags),
                ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT r.* FROM recipes r WHERE lower(r.title) LIKE lower(?) ORDER BY {order_by}",
                (f"%{name_substring}%",),
            ).fetchall()
    return [_row_to_recipe(r) for r in rows]
