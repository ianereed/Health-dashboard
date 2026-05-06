"""Tests for preprocess_images.py."""
from __future__ import annotations

import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _PIL_AVAILABLE, reason="Pillow not installed")


def _make_test_image(path: pathlib.Path, width: int = 4000, height: int = 3000) -> None:
    """Write a synthetic RGB JPEG for testing."""
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    img.save(path, "JPEG", quality=90)


def test_resize_long_edge(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    _make_test_image(src / "IMG_0001.jpg", width=4000, height=3000)

    from preprocess_images import _process_one
    log = dst / "preprocess_log.jsonl"
    dst.mkdir()
    _process_one(src / "IMG_0001.jpg", dst / "IMG_0001.jpg", max_dim=1500,
                 autocontrast_cutoff=2, log_path=log)

    from PIL import Image as PILImage
    result = PILImage.open(dst / "IMG_0001.jpg")
    w, h = result.size
    assert max(w, h) <= 1500, f"long edge {max(w, h)} exceeds 1500"


def test_output_is_rgb_not_grayscale(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    _make_test_image(src / "IMG_0002.jpg", width=800, height=600)

    from preprocess_images import _process_one
    log = dst / "preprocess_log.jsonl"
    _process_one(src / "IMG_0002.jpg", dst / "IMG_0002.jpg", max_dim=1500,
                 autocontrast_cutoff=2, log_path=log)

    from PIL import Image as PILImage
    result = PILImage.open(dst / "IMG_0002.jpg")
    assert result.mode == "RGB", f"expected RGB, got {result.mode}"


def test_idempotent(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    _make_test_image(src / "IMG_0003.jpg", width=2000, height=1500)

    from preprocess_images import _process_one
    log = dst / "preprocess_log.jsonl"

    # First run
    _process_one(src / "IMG_0003.jpg", dst / "IMG_0003.jpg", max_dim=1500,
                 autocontrast_cutoff=2, log_path=log)
    mtime_after_first = (dst / "IMG_0003.jpg").stat().st_mtime

    # Tiny sleep to ensure clock advances if a write would happen
    time.sleep(0.05)

    # Second run — should be no-op (dst mtime > src mtime)
    _process_one(src / "IMG_0003.jpg", dst / "IMG_0003.jpg", max_dim=1500,
                 autocontrast_cutoff=2, log_path=log)
    mtime_after_second = (dst / "IMG_0003.jpg").stat().st_mtime

    assert mtime_after_second == mtime_after_first, "second run should not modify the file"

    # Log should have exactly one entry (first run only)
    entries = [line for line in log.read_text().splitlines() if line.strip()]
    assert len(entries) == 1, f"expected 1 log entry, got {len(entries)}"
