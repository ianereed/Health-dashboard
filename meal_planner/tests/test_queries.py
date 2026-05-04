from pathlib import Path

import pytest

from meal_planner.db import add_recipe_tag, init_db, insert_ingredient, insert_recipe
from meal_planner.queries import get_recipe, list_recipes, search_recipes


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "recipes.db"
    init_db(p)
    return p


@pytest.fixture
def seeded_db(db_path: Path) -> Path:
    r1 = insert_recipe(title="Chicken Soup", base_servings=4, path=db_path)
    r2 = insert_recipe(title="Beef Stew", base_servings=6, path=db_path)
    r3 = insert_recipe(title="Veggie Stir Fry", base_servings=2, path=db_path)
    add_recipe_tag(r1, "asian", path=db_path)
    add_recipe_tag(r1, "soup", path=db_path)
    add_recipe_tag(r2, "hearty", path=db_path)
    add_recipe_tag(r3, "asian", path=db_path)
    add_recipe_tag(r3, "vegetarian", path=db_path)
    return db_path


def test_list_recipes_empty(db_path: Path) -> None:
    assert list_recipes(path=db_path) == []


def test_list_recipes_populated(seeded_db: Path) -> None:
    recipes = list_recipes(path=seeded_db)
    assert len(recipes) == 3
    titles = [r.title for r in recipes]
    assert titles == sorted(titles)  # ordered by title


def test_list_recipes_tag_filter(seeded_db: Path) -> None:
    asian = list_recipes(tag="asian", path=seeded_db)
    assert {r.title for r in asian} == {"Chicken Soup", "Veggie Stir Fry"}

    soup_only = list_recipes(tag="soup", path=seeded_db)
    assert [r.title for r in soup_only] == ["Chicken Soup"]

    no_match = list_recipes(tag="nonexistent", path=seeded_db)
    assert no_match == []


def test_get_recipe_existing(seeded_db: Path) -> None:
    all_recipes = list_recipes(path=seeded_db)
    for r in all_recipes:
        fetched = get_recipe(r.id, path=seeded_db)
        assert fetched.title == r.title
        assert fetched.id == r.id


def test_get_recipe_missing_raises(seeded_db: Path) -> None:
    with pytest.raises(KeyError):
        get_recipe(99999, path=seeded_db)


def test_search_recipes_name_substring(seeded_db: Path) -> None:
    results = search_recipes(name_substring="stir", path=seeded_db)
    assert [r.title for r in results] == ["Veggie Stir Fry"]

    results_ci = search_recipes(name_substring="SOUP", path=seeded_db)
    assert [r.title for r in results_ci] == ["Chicken Soup"]

    all_results = search_recipes(name_substring="", path=seeded_db)
    assert len(all_results) == 3


def test_search_recipes_tags_single(seeded_db: Path) -> None:
    results = search_recipes(tags=("asian",), path=seeded_db)
    assert {r.title for r in results} == {"Chicken Soup", "Veggie Stir Fry"}


def test_search_recipes_tags_multi(seeded_db: Path) -> None:
    # Only Veggie Stir Fry has both "asian" AND "vegetarian"
    results = search_recipes(tags=("asian", "vegetarian"), path=seeded_db)
    assert [r.title for r in results] == ["Veggie Stir Fry"]


def test_search_recipes_name_and_tags(seeded_db: Path) -> None:
    # name contains "chicken" AND has "asian" tag
    results = search_recipes(name_substring="chicken", tags=("asian",), path=seeded_db)
    assert [r.title for r in results] == ["Chicken Soup"]

    # name contains "beef" AND has "asian" tag — no match
    results_none = search_recipes(name_substring="beef", tags=("asian",), path=seeded_db)
    assert results_none == []
