from __future__ import annotations

from pathlib import Path

from meal_planner.models import Recipe


def list_recipes(*, tag: str | None = None, path: Path | None = None) -> list[Recipe]:
    raise NotImplementedError


def get_recipe(recipe_id: int, *, path: Path | None = None) -> Recipe:
    raise NotImplementedError


def search_recipes(
    *,
    name_substring: str = "",
    tags: list[str] = (),
    path: Path | None = None,
) -> list[Recipe]:
    raise NotImplementedError
