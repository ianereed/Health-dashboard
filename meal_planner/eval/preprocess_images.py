"""preprocess_images.py — Resize + autocontrast recipe photos for bake-off.

Applies three operations per photo:
1. EXIF rotation correction (ImageOps.exif_transpose)
2. Thumbnail resize to max_dim on long edge (default 1500px)
3. Autocontrast stretch (ImageOps.autocontrast, default cutoff=2)

Does NOT grayscale or deskew. Saves as JPEG quality 90.
Copies .golden.json sidecar files unchanged so _load_corpus() keeps working.
Idempotent: skips output file if dst mtime > src mtime.

Usage:
    python3 preprocess_images.py --src CORPUS_DIR --dst CORPUS_DIR_OUT
                                 [--max-dim 1500] [--autocontrast-cutoff 2]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

try:
    from PIL import Image, ImageOps
except ImportError:
    print("error: Pillow not installed. Run: pip install 'Pillow>=10.0'", file=sys.stderr)
    sys.exit(1)

_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".PNG"})


def _process_one(
    src: pathlib.Path,
    dst: pathlib.Path,
    max_dim: int,
    autocontrast_cutoff: int,
    log_path: pathlib.Path,
) -> None:
    """Process a single image src → dst. Append to log_path."""
    if dst.exists() and dst.stat().st_mtime > src.stat().st_mtime:
        return  # idempotent: already up to date

    img = Image.open(src)
    orig_w, orig_h = img.size

    # EXIF rotation
    img = ImageOps.exif_transpose(img)

    # Convert to RGB (handles palette images, RGBA, etc.)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Resize long edge to max_dim
    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    final_w, final_h = img.size

    # Autocontrast
    img = ImageOps.autocontrast(img, cutoff=autocontrast_cutoff)

    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "JPEG", quality=90)

    entry = {
        "src": str(src),
        "dst": str(dst),
        "orig_w": orig_w,
        "orig_h": orig_h,
        "final_w": final_w,
        "final_h": final_h,
        "applied_ops": ["exif_transpose", f"thumbnail_{max_dim}", f"autocontrast_{autocontrast_cutoff}"],
        "ts": time.time(),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, metavar="PATH", help="Source corpus directory.")
    parser.add_argument("--dst", required=True, metavar="PATH", help="Output directory.")
    parser.add_argument("--max-dim", type=int, default=1500, metavar="INT",
                        help="Max dimension (long edge) in pixels (default 1500).")
    parser.add_argument("--autocontrast-cutoff", type=int, default=2, metavar="INT",
                        help="Autocontrast cutoff %% (default 2).")
    args = parser.parse_args()

    src_dir = pathlib.Path(args.src)
    dst_dir = pathlib.Path(args.dst)

    if not src_dir.exists():
        print(f"error: src dir not found: {src_dir}", file=sys.stderr)
        sys.exit(1)

    dst_dir.mkdir(parents=True, exist_ok=True)
    log_path = dst_dir / "preprocess_log.jsonl"

    photos = sorted(p for p in src_dir.iterdir() if p.suffix in _IMAGE_SUFFIXES)
    if not photos:
        print(f"no images found in {src_dir}", file=sys.stderr)
        sys.exit(1)

    n_processed = 0
    n_skipped = 0
    for src_photo in photos:
        dst_photo = dst_dir / (src_photo.stem + ".jpg")
        before_mtime = dst_photo.stat().st_mtime if dst_photo.exists() else None
        _process_one(src_photo, dst_photo, args.max_dim, args.autocontrast_cutoff, log_path)
        after_mtime = dst_photo.stat().st_mtime if dst_photo.exists() else None
        if before_mtime is not None and after_mtime == before_mtime:
            n_skipped += 1
            print(f"  skip (up-to-date): {dst_photo.name}", file=sys.stderr)
        else:
            n_processed += 1
            print(f"  processed: {src_photo.name} → {dst_photo.name}", file=sys.stderr)

        # Copy golden sidecar
        golden_src = src_photo.parent / f"{src_photo.stem}.golden.json"
        if golden_src.exists():
            golden_dst = dst_dir / f"{src_photo.stem}.golden.json"
            golden_dst.write_bytes(golden_src.read_bytes())

    print(f"done: {n_processed} processed, {n_skipped} skipped → {dst_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
