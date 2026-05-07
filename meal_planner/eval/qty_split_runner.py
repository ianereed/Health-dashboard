"""Run extract_recipe_from_photo over the eval corpus and dump JSONL.

Read-only experiment — does not touch recipes.db or any production state.
Used to measure qty/unit split rate after a prompt change.

Usage:
  python -m meal_planner.eval.qty_split_runner \\
    --corpus meal_planner/eval/recipe_photos_processed \\
    --out /tmp/qty_split_v1.jsonl \\
    [--prompt /tmp/v1_prompt.txt]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from meal_planner.vision import _ollama
from meal_planner.vision.extract import extract_recipe_from_photo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--prompt", type=Path, help="Override prompt file (optional)")
    ap.add_argument("--limit", type=int, default=0, help="Stop after N photos (0 = all)")
    args = ap.parse_args()

    if args.prompt:
        _ollama._PROMPT_TEXT = args.prompt.read_text()
        print(f"[prompt] loaded override from {args.prompt} ({len(_ollama._PROMPT_TEXT)} chars)")
    else:
        _ollama._PROMPT_TEXT = None  # force reload from package
        text = _ollama.load_prompt()
        print(f"[prompt] using default ({len(text)} chars)")

    photos = sorted(p for p in args.corpus.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if args.limit:
        photos = photos[: args.limit]
    print(f"[corpus] {len(photos)} photos from {args.corpus}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        for i, photo in enumerate(photos, 1):
            t0 = time.time()
            print(f"[{i}/{len(photos)}] {photo.name}…", flush=True)
            try:
                r = extract_recipe_from_photo(
                    photo, timeout_s=500, num_ctx=4096, keep_alive="300s"
                )
                row = {
                    "photo": photo.name,
                    "status": r.status,
                    "latency_s": r.latency_s,
                    "n_retries": r.n_retries,
                    "error": r.error,
                    "extracted": r.parsed,
                    "wall_s": round(time.time() - t0, 2),
                }
            except Exception as exc:
                row = {
                    "photo": photo.name,
                    "status": "runner_error",
                    "error": repr(exc),
                    "extracted": None,
                    "wall_s": round(time.time() - t0, 2),
                }
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(f"  → status={row['status']} wall={row['wall_s']}s", flush=True)
    print(f"\nDone. Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
