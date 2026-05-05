"""Tests for _load_corpus: photo-golden pairing and case-insensitive suffix handling."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from bake_off import _load_corpus  # noqa: E402


def test_load_corpus_pairs_photos_with_goldens(tmp_path, capsys):
    """2 photos + 1 golden: returns 1 pair and warns about the unpaired photo.

    Also exercises .JPG uppercase suffix (Amendment A).
    """
    # Photo 1: has a matching golden (uppercase .JPG — iPhone naming convention)
    photo1 = tmp_path / "recipe1.JPG"
    photo1.write_bytes(b"\xff\xd8\xff")  # minimal JPEG magic bytes

    golden1 = tmp_path / "recipe1.golden.json"
    golden_data = {
        "title": "Test Recipe",
        "ingredients": [{"qty": "1", "unit": "cup", "name": "flour"}],
        "tags": ["baking"],
    }
    golden1.write_text(json.dumps(golden_data), encoding="utf-8")

    # Photo 2: no golden
    photo2 = tmp_path / "recipe2.jpg"
    photo2.write_bytes(b"\xff\xd8\xff")

    pairs = _load_corpus(tmp_path)

    assert len(pairs) == 1
    assert pairs[0][0] == photo1
    assert pairs[0][1]["title"] == "Test Recipe"

    # Warning about unpaired photo
    captured = capsys.readouterr()
    assert "recipe2" in captured.err
    assert "warning" in captured.err.lower()
