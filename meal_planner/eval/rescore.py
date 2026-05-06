"""rescore.py — Re-score existing bake-off results with updated normalization.

Reads runs.jsonl from a results dir, re-calls _score() on every scored row,
writes runs.rescored.jsonl + summary.rescored.json (originals untouched), and
prints a per-model delta table.

Usage:
    python3 rescore.py [--in RESULTS_DIR | latest] [--corpus CORPUS_DIR]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

_EVAL_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(_EVAL_DIR))

from bake_off import (  # noqa: E402
    _load_corpus,
    _load_synonyms,
    _resolve_resume_dir,
    _score,
)

_RESULTS_ROOT = _EVAL_DIR / "results"
_DEFAULT_CORPUS = _EVAL_DIR / "recipe_photos"


def _rescore_dir(in_dir: pathlib.Path, corpus_dir: pathlib.Path) -> dict:
    """Re-score all scored rows in in_dir/runs.jsonl.

    Returns a dict: {model: {title_accuracy_mean, ingredient_f1_mean, ...}}
    for both the original scores and the rescored values.
    """
    runs_path = in_dir / "runs.jsonl"
    if not runs_path.exists():
        raise FileNotFoundError(f"runs.jsonl not found in {in_dir}")

    # Load corpus goldens (keyed by photo basename)
    pairs = _load_corpus(corpus_dir)
    golden_by_photo: dict[str, dict] = {p.name: g for p, g in pairs}

    synonyms = _load_synonyms()
    fractions = synonyms.get("unicode_fractions", {})

    rows_in: list[dict] = []
    with runs_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows_in.append(json.loads(line))

    rows_out: list[dict] = []
    for row in rows_in:
        if row.get("status") != "scored" or row.get("extracted") is None:
            rows_out.append(row)
            continue

        golden = golden_by_photo.get(row["photo"])
        if golden is None:
            print(f"  warning: no golden for {row['photo']}, skipping rescore", file=sys.stderr)
            rows_out.append(row)
            continue

        new_score = _score(row["extracted"], golden, synonyms, fractions)
        new_row = dict(row)
        new_row["score"] = new_score
        rows_out.append(new_row)

    # Write rescored jsonl
    out_path = in_dir / "runs.rescored.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows_out:
            f.write(json.dumps(row) + "\n")

    # Compute per-model stats for both original and rescored
    orig_by_model: dict[str, list[dict]] = {}
    new_by_model: dict[str, list[dict]] = {}
    for orig, new in zip(rows_in, rows_out):
        if orig.get("status") != "scored":
            continue
        m = orig["model"]
        orig_by_model.setdefault(m, []).append(orig)
        new_by_model.setdefault(m, []).append(new)

    def _mean(rows: list[dict], key: str) -> float | None:
        vals = [r["score"][key] for r in rows if r.get("score") and r["score"].get(key) is not None]
        return statistics.mean(vals) if vals else None

    stats: dict[str, dict] = {}
    for model in orig_by_model:
        orig_rows = orig_by_model[model]
        new_rows = new_by_model.get(model, [])
        stats[model] = {
            "n": len(orig_rows),
            "orig_f1": _mean(orig_rows, "ingredient_f1"),
            "rescored_f1": _mean(new_rows, "ingredient_f1"),
            "orig_title": _mean(orig_rows, "title_accuracy"),
            "rescored_title": _mean(new_rows, "title_accuracy"),
        }

    # Write summary.rescored.json
    summary_path = in_dir / "summary.rescored.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump({"models": stats}, f, indent=2)

    return stats


def _fmt(v: float | None) -> str:
    return f"{v:.3f}" if v is not None else "  n/a"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in",
        dest="in_dir",
        default="latest",
        help="Results dir path or 'latest' (default: latest)",
    )
    parser.add_argument(
        "--corpus",
        default=str(_DEFAULT_CORPUS),
        help=f"Corpus dir with photos + goldens (default: {_DEFAULT_CORPUS})",
    )
    args = parser.parse_args()

    in_dir = _resolve_resume_dir(args.in_dir, _RESULTS_ROOT)
    corpus_dir = pathlib.Path(args.corpus)
    if not corpus_dir.exists():
        print(f"error: corpus dir not found: {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Rescoring: {in_dir}")
    stats = _rescore_dir(in_dir, corpus_dir)

    # Print delta table
    print()
    print(f"{'Model':<25} | {'n':>3} | {'f1 orig':>7} → {'rescored':>8} | {'title orig':>10} → {'rescored':>8}")
    print("-" * 75)
    for model, s in sorted(stats.items()):
        f1_orig = _fmt(s["orig_f1"])
        f1_new = _fmt(s["rescored_f1"])
        t_orig = _fmt(s["orig_title"])
        t_new = _fmt(s["rescored_title"])
        print(f"{model:<25} | {s['n']:>3} | {f1_orig:>7} → {f1_new:>8} | {t_orig:>10} → {t_new:>8}")
    print()

    out_jsonl = in_dir / "runs.rescored.jsonl"
    out_summary = in_dir / "summary.rescored.json"
    print(f"Written: {out_jsonl}")
    print(f"Written: {out_summary}")


if __name__ == "__main__":
    main()
