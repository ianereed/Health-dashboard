from __future__ import annotations

from meal_planner.tag_categories import CATEGORY_MAP, _partition_tags_by_category


def test_partition_known_tags() -> None:
    tags = ["chicken", "italian", "pork", "asian"]
    result = _partition_tags_by_category(tags, CATEGORY_MAP)
    assert result["cuisine"] == ["italian", "asian"]
    assert result["meat_or_diet"] == ["chicken", "pork"]
    assert result["other"] == []


def test_partition_unknown_tags_fall_to_other() -> None:
    tags = ["soup", "hearty", "easy"]
    result = _partition_tags_by_category(tags, CATEGORY_MAP)
    assert result["cuisine"] == []
    assert result["meat_or_diet"] == []
    assert result["other"] == ["soup", "hearty", "easy"]


def test_partition_preserves_order() -> None:
    tags = ["soup", "italian", "chicken", "baked", "japanese", "tofu"]
    result = _partition_tags_by_category(tags, CATEGORY_MAP)
    assert result["cuisine"] == ["italian", "japanese"]
    assert result["meat_or_diet"] == ["chicken", "tofu"]
    assert result["other"] == ["soup", "baked"]


def test_partition_empty_input() -> None:
    result = _partition_tags_by_category([], CATEGORY_MAP)
    assert result == {"cuisine": [], "meat_or_diet": [], "other": []}


def test_partition_no_duplicate_tag_in_two_buckets() -> None:
    tags = list(CATEGORY_MAP.keys()) + ["soup", "hearty", "easy"]
    result = _partition_tags_by_category(tags, CATEGORY_MAP)
    all_placed = result["cuisine"] + result["meat_or_diet"] + result["other"]
    assert len(all_placed) == len(tags)
    assert set(all_placed) == set(tags)


def test_category_map_keys_are_lowercase() -> None:
    for key in CATEGORY_MAP:
        assert key == key.lower(), f"CATEGORY_MAP key {key!r} is not lowercase"
