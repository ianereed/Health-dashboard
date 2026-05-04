from __future__ import annotations

from pathlib import Path

from meal_planner.models import Ingredient, Recipe


def scale_ingredients(
    recipe: Recipe,
    target_servings: int,
    *,
    path: Path | None = None,
) -> list[Ingredient]:
    """Return ingredients scaled to target_servings.

    qty_per_serving is multiplied by target_servings; None stays None.
    Returned Ingredient.id mirrors the source row — no new DB rows created.
    Results are ordered by sort_order.
    """
    from meal_planner import db as _db

    p = path or _db.DB_PATH
    with _db._get_conn(p) as conn:
        rows = conn.execute(
            "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY sort_order",
            (recipe.id,),
        ).fetchall()

    result = []
    for row in rows:
        qty = row["qty_per_serving"]
        result.append(
            Ingredient(
                id=row["id"],
                recipe_id=row["recipe_id"],
                name=row["name"],
                qty_per_serving=qty * target_servings if qty is not None else None,
                unit=row["unit"],
                notes=row["notes"],
                todoist_section=row["todoist_section"],
                sort_order=row["sort_order"],
            )
        )
    return result
