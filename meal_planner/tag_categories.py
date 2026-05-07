"""Tag category map for the Recipes tab pill filter (Phase 17 Chunk A).

Tags are partitioned into three display groups: cuisine, meat_or_diet, other.
Unknown tags fall through to 'other'. The map is hardcoded; DB schema is
unchanged.
"""
from __future__ import annotations

CATEGORY_MAP: dict[str, str] = {
    # cuisine / country
    "asian": "cuisine",
    "canadian": "cuisine",
    "chinese": "cuisine",
    "italian": "cuisine",
    "japanese": "cuisine",
    "mexican": "cuisine",
    # meat type / diet
    "chicken": "meat_or_diet",
    "pork": "meat_or_diet",
    "sausage": "meat_or_diet",
    "seafood": "meat_or_diet",
    "tofu": "meat_or_diet",
    "vegetarian": "meat_or_diet",
}

_CATEGORY_ORDER = ("cuisine", "meat_or_diet", "other")


def _partition_tags_by_category(
    tags: list[str], category_map: dict[str, str]
) -> dict[str, list[str]]:
    """Group tags into ('cuisine', 'meat_or_diet', 'other') buckets.

    Each bucket preserves the input order. Unknown tags fall through to 'other'.
    Returns a dict with all three keys, even if some buckets are empty.
    """
    buckets: dict[str, list[str]] = {cat: [] for cat in _CATEGORY_ORDER}
    for tag in tags:
        cat = category_map.get(tag, "other")
        buckets[cat].append(tag)
    return buckets
