from pathlib import Path

import pytest

from meal_planner.db import add_recipe_tag, init_db, insert_ingredient, insert_recipe
from meal_planner.queries import get_recipe, list_all_tags, list_recipes, search_recipes


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


def test_search_recipes_tags_dedup(seeded_db: Path) -> None:
    # duplicate tag in input must produce same results as single occurrence
    deduped = search_recipes(tags=("asian", "asian"), path=seeded_db)
    single = search_recipes(tags=("asian",), path=seeded_db)
    assert {r.id for r in deduped} == {r.id for r in single}


def test_list_all_tags_returns_sorted_distinct_linked_tags(db_path: Path) -> None:
    """Orphan tags (no recipe_tags row) are excluded; result is sorted."""
    import sqlite3 as _sqlite3

    r1 = insert_recipe(title="A", base_servings=2, path=db_path)
    r2 = insert_recipe(title="B", base_servings=2, path=db_path)
    add_recipe_tag(r1, "soup", path=db_path)
    add_recipe_tag(r1, "asian", path=db_path)
    add_recipe_tag(r2, "hearty", path=db_path)

    # Insert orphan tag directly — no recipe_tags row
    conn = _sqlite3.connect(db_path)
    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES ('orphan')")
    conn.commit()
    conn.close()

    tags = list_all_tags(path=db_path)
    assert tags == ["asian", "hearty", "soup"]
    assert "orphan" not in tags


def test_search_recipes_tag_logic_or_returns_union(seeded_db: Path) -> None:
    """OR logic returns all recipes that have ANY of the listed tags."""
    # Chicken Soup: asian, soup; Beef Stew: hearty; Veggie Stir Fry: asian, vegetarian
    results = search_recipes(tags=("soup", "vegetarian"), tag_logic="or", path=seeded_db)
    titles = {r.title for r in results}
    assert titles == {"Chicken Soup", "Veggie Stir Fry"}


def test_search_recipes_tag_logic_and_returns_intersection(seeded_db: Path) -> None:
    """AND logic returns only recipes that have ALL listed tags."""
    results = search_recipes(tags=("asian", "vegetarian"), tag_logic="and", path=seeded_db)
    assert [r.title for r in results] == ["Veggie Stir Fry"]


def test_search_recipes_empty_tags_returns_all_regardless_of_logic(seeded_db: Path) -> None:
    """Empty tags tuple returns all recipes for both AND and OR logic."""
    and_results = search_recipes(tags=(), tag_logic="and", path=seeded_db)
    or_results = search_recipes(tags=(), tag_logic="or", path=seeded_db)
    assert len(and_results) == 3
    assert len(or_results) == 3


def test_search_recipes_invalid_tag_logic_raises(seeded_db: Path) -> None:
    with pytest.raises(ValueError, match="tag_logic"):
        search_recipes(tags=("asian",), tag_logic="xor", path=seeded_db)


def test_get_recipe_roundtrip_all_fields(db_path: Path) -> None:
    rid = insert_recipe(
        title="Full Recipe",
        base_servings=6,
        instructions="Mix and bake.",
        cook_time_min=45,
        source="Grandma",
        photo_path="/photos/full.jpg",
        path=db_path,
    )
    r = get_recipe(rid, path=db_path)
    assert r.title == "Full Recipe"
    assert r.base_servings == 6
    assert r.instructions == "Mix and bake."
    assert r.cook_time_min == 45
    assert r.source == "Grandma"
    assert r.photo_path == "/photos/full.jpg"
    assert r.created_at is not None
    assert r.updated_at is not None
