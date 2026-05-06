"""compare.py — Side-by-side comparison of multiple bake-off result directories.

Reads summary.json (or summary.rescored.json if present) from each directory and
prints a per-model delta table across all directories.

Usage:
    python3 compare.py DIR_A DIR_B [DIR_C ...]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def _load_summary(d: pathlib.Path) -> dict:
    """Load summary from a result dir. Prefers summary.rescored.json if present."""
    rescored = d / "summary.rescored.json"
    base = d / "summary.json"
    if rescored.exists():
        return json.loads(rescored.read_text(encoding="utf-8"))
    if base.exists():
        return json.loads(base.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"no summary.json or summary.rescored.json in {d}")


def _fmt(v: float | None) -> str:
    return f"{v:.3f}" if v is not None else "  n/a"


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "   n/a"
    diff = b - a
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.3f}"


def _get_metric(summary: dict, model: str, metric: str) -> float | None:
    """Extract a metric from a summary dict. Handles both summary.json and summary.rescored.json shapes."""
    models = summary.get("models", {})
    if isinstance(models, list):
        # summary.json shape: list of dicts with "model" key
        for m in models:
            if m.get("model") == model:
                if metric == "f1":
                    return m.get("rescored_f1") or m.get("ingredient_f1_mean")
                if metric == "title":
                    return m.get("rescored_title") or m.get("title_accuracy_mean")
                if metric == "struct":
                    return m.get("structural_validity_rate")
                if metric == "cold_p95":
                    return m.get("cold_load_p95")
        return None
    if isinstance(models, dict):
        # summary.rescored.json shape: dict keyed by model name
        m = models.get(model, {})
        if metric == "f1":
            return m.get("rescored_f1") or m.get("ingredient_f1_mean")
        if metric == "title":
            return m.get("rescored_title") or m.get("title_accuracy_mean")
        if metric == "struct":
            return m.get("structural_validity_rate")
        if metric == "cold_p95":
            return m.get("cold_load_p95")
    return None


def _collect_models(summaries: list[dict]) -> list[str]:
    """Collect all model names across all summaries, preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for s in summaries:
        models = s.get("models", {})
        if isinstance(models, list):
            names = [m.get("model", "") for m in models]
        else:
            names = list(models.keys())
        for name in names:
            if name and name not in seen:
                seen.add(name)
                result.append(name)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dirs", nargs="+", metavar="DIR", help="Result directories to compare.")
    args = parser.parse_args()

    dirs = [pathlib.Path(d) for d in args.dirs]
    summaries: list[dict] = []
    labels: list[str] = []
    checksums: list[str | None] = []

    for d in dirs:
        if not d.exists():
            print(f"error: directory not found: {d}", file=sys.stderr)
            sys.exit(1)
        try:
            s = _load_summary(d)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
        summaries.append(s)
        labels.append(d.name)
        checksums.append(s.get("corpus_checksum"))

    # Warn on corpus checksum mismatch
    defined = [c for c in checksums if c is not None]
    if len(set(defined)) > 1:
        print("WARNING: corpus_checksum differs across directories — results may not be comparable.", file=sys.stderr)
        for label, ck in zip(labels, checksums):
            print(f"  {label}: {ck}", file=sys.stderr)

    models = _collect_models(summaries)
    metrics = [("f1", "ingredient_f1"), ("title", "title_acc"), ("struct", "struct_rate"), ("cold_p95", "cold_p95_s")]

    # Header
    col_w = 10
    model_w = 28
    dir_header = " | ".join(f"{lbl[:col_w]:<{col_w}}" for lbl in labels)
    print(f"\n{'Model':<{model_w}} | metric     | {dir_header} | Δ(A→last)")
    print("-" * (model_w + 3 + 12 + len(labels) * (col_w + 3) + 12))

    for model in models:
        vals_by_metric: dict[str, list[float | None]] = {}
        for metric_key, _ in metrics:
            vals_by_metric[metric_key] = [_get_metric(s, model, metric_key) for s in summaries]

        first_row = True
        for metric_key, metric_label in metrics:
            vals = vals_by_metric[metric_key]
            dir_vals = " | ".join(f"{_fmt(v):>{col_w}}" for v in vals)
            delta = _delta(vals[0], vals[-1]) if len(vals) >= 2 else "   n/a"
            model_col = model if first_row else ""
            print(f"{model_col:<{model_w}} | {metric_label:<10} | {dir_vals} | {delta:>9}")
            first_row = False
        print()


if __name__ == "__main__":
    main()
