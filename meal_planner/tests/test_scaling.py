from pathlib import Path

import pytest

from meal_planner.db import init_db, insert_ingredient, insert_recipe
from meal_planner.queries import get_recipe
from meal_planner.scaling import scale_ingredients


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "recipes.db"
    init_db(p)
    return p


def _make_recipe(db_path: Path, base_servings: int = 4) -> int:
    return insert_recipe(title="Test Recipe", base_servings=base_servings, path=db_path)


def test_scale_1x(db_path: Path) -> None:
    rid = _make_recipe(db_path, base_servings=4)
    insert_ingredient(recipe_id=rid, name="flour", qty_per_serving=0.5, unit="cup", path=db_path)
    recipe = get_recipe(rid, path=db_path)
    scaled = scale_ingredients(recipe, 4, path=db_path)
    assert len(scaled) == 1
    assert scaled[0].qty_per_serving == pytest.approx(2.0)


def test_scale_2x(db_path: Path) -> None:
    rid = _make_recipe(db_path, base_servings=2)
    insert_ingredient(recipe_id=rid, name="water", qty_per_serving=1.0, unit="cup", path=db_path)
    recipe = get_recipe(rid, path=db_path)
    scaled = scale_ingredients(recipe, 4, path=db_path)
    assert scaled[0].qty_per_serving == pytest.approx(4.0)


def test_scale_half(db_path: Path) -> None:
    rid = _make_recipe(db_path, base_servings=4)
    insert_ingredient(recipe_id=rid, name="salt", qty_per_serving=1.0, unit="tsp", path=db_path)
    recipe = get_recipe(rid, path=db_path)
    scaled = scale_ingredients(recipe, 2, path=db_path)
    assert scaled[0].qty_per_serving == pytest.approx(2.0)


def test_countable_ingredient_stays_none(db_path: Path) -> None:
    rid = _make_recipe(db_path)
    insert_ingredient(recipe_id=rid, name="egg", qty_per_serving=None, unit=None, path=db_path)
    recipe = get_recipe(rid, path=db_path)
    scaled = scale_ingredients(recipe, 3, path=db_path)
    assert scaled[0].qty_per_serving is None


def test_preserves_sort_order(db_path: Path) -> None:
    rid = _make_recipe(db_path)
    insert_ingredient(recipe_id=rid, name="b_item", qty_per_serving=1.0, unit="g", sort_order=2, path=db_path)
    insert_ingredient(recipe_id=rid, name="a_item", qty_per_serving=2.0, unit="g", sort_order=1, path=db_path)
    recipe = get_recipe(rid, path=db_path)
    scaled = scale_ingredients(recipe, 1, path=db_path)
    assert scaled[0].name == "a_item"
    assert scaled[1].name == "b_item"


def test_preserves_todoist_section_and_notes(db_path: Path) -> None:
    rid = _make_recipe(db_path)
    insert_ingredient(
        recipe_id=rid,
        name="garlic",
        qty_per_serving=2.0,
        unit="clove",
        notes="minced",
        todoist_section="Produce",
        path=db_path,
    )
    recipe = get_recipe(rid, path=db_path)
    scaled = scale_ingredients(recipe, 2, path=db_path)
    assert scaled[0].notes == "minced"
    assert scaled[0].todoist_section == "Produce"
