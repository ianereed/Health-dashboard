"""Replay a runs.jsonl through normalize_extraction, recompute split metrics.

Usage:
  python -m meal_planner.eval.replay_normalize \\
    --runs meal_planner/eval/results/2026-05-06-warm-llama32/runs.jsonl \\
    --corpus meal_planner/eval/recipe_photos_processed \\
    --out meal_planner/eval/results/option-b-replay-baseline/

Reads runs.jsonl, applies normalize_extraction to each `extracted` dict, writes:
  out/runs.normalized.jsonl  — same rows but normalized
  out/summary.json           — {before: {...}, after: {...}, delta: {...}}
  out/per_photo.md           — markdown table per photo: before vs after counts
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from meal_planner.eval.bake_off import _SYNONYMS_PATH, _score
from meal_planner.eval.qty_split_scorer import classify_ingredient, load_golden
from meal_planner.vision._normalize import normalize_extraction


def _compute_metrics(rows: list[dict], corpus_dir: Path, syn_doc: dict, fractions: dict) -> dict:
    agg = {k: 0 for k in ("split_ok", "qty_unit_fused", "unit_in_name", "qty_only_no_unit", "present")}
    f1s, titles = [], []
    per_photo = []

    for r in rows:
        photo = r["photo"]
        extracted = r.get("extracted") or {}
        golden = load_golden(corpus_dir, photo) or {"title": "", "ingredients": [], "tags": []}
        counts = {k: 0 for k in agg}

        for ing in extracted.get("ingredients", []):
            c = classify_ingredient(ing)
            if c == "qty_empty":
                continue
            counts[c] += 1
            counts["present"] += 1

        # Accept ok/scored/parsed_ok as scoreable (different run formats)
        if r.get("status") in ("ok", "scored", "parsed_ok") and extracted:
            sc = _score(extracted, golden, syn_doc, fractions)
        else:
            sc = {"title_accuracy": 0.0, "ingredient_f1": 0.0}

        for k in agg:
            agg[k] += counts[k]
        f1s.append(sc["ingredient_f1"])
        titles.append(sc["title_accuracy"])
        per_photo.append({"photo": photo, "counts": counts, "f1": sc["ingredient_f1"]})

    n = max(1, agg["present"])
    return {
        "n_photos": len(rows),
        "split_rate": agg["split_ok"] / n,
        "scale_ok_rate": (agg["split_ok"] + agg["qty_only_no_unit"]) / n,
        "qty_unit_fused_rate": agg["qty_unit_fused"] / n,
        "unit_in_name_rate": agg["unit_in_name"] / n,
        "ingredients_present": agg["present"],
        "ingredient_f1_mean": sum(f1s) / max(1, len(f1s)),
        "title_accuracy_mean": sum(titles) / max(1, len(titles)),
        "agg": agg,
        "per_photo": per_photo,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True, type=Path)
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    syn_doc = yaml.safe_load(_SYNONYMS_PATH.read_text())
    fractions = syn_doc.get("unicode_fractions", {})

    all_rows = [json.loads(l) for l in args.runs.read_text().splitlines() if l.strip()]
    # Deduplicate: keep the last row per photo that has extracted data.
    # Baseline runs.jsonl uses multi-step statuses (pending/calling/parsed_ok/scored);
    # V1 runs.jsonl uses single-row-per-photo format (ok/timeout).
    seen: dict[str, dict] = {}
    for r in all_rows:
        if r.get("extracted"):
            seen[r["photo"]] = r
    rows = list(seen.values())

    # Build normalized rows
    norm_rows = []
    all_norm_warnings: list[str] = []
    for r in rows:
        extracted = r.get("extracted")
        if extracted:
            norm_extracted, w = normalize_extraction(extracted)
            all_norm_warnings.extend(w)
        else:
            norm_extracted = extracted
        norm_rows.append({**r, "extracted": norm_extracted})

    before = _compute_metrics(rows, args.corpus, syn_doc, fractions)
    after = _compute_metrics(norm_rows, args.corpus, syn_doc, fractions)

    def _delta(key: str) -> float:
        return round(after[key] - before[key], 4)

    delta = {
        "scale_ok_rate": _delta("scale_ok_rate"),
        "qty_unit_fused_rate": _delta("qty_unit_fused_rate"),
        "unit_in_name_rate": _delta("unit_in_name_rate"),
        "ingredient_f1_mean": _delta("ingredient_f1_mean"),
        "title_accuracy_mean": _delta("title_accuracy_mean"),
    }

    summary = {"before": before, "after": after, "delta": delta}

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "runs.normalized.jsonl").write_text(
        "\n".join(json.dumps(r, default=str) for r in norm_rows) + "\n"
    )
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    # per_photo.md
    md_lines = [
        "# Per-photo: before vs after normalize\n",
        f"| photo | fused_before | fused_after | name_unit_before | name_unit_after | scale_ok_before | scale_ok_after | F1_before | F1_after |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for pb, pa in zip(before["per_photo"], after["per_photo"]):
        cb, ca = pb["counts"], pa["counts"]
        n_b = max(1, cb["present"])
        n_a = max(1, ca["present"])
        md_lines.append(
            f"| {pb['photo']} "
            f"| {cb['qty_unit_fused']} | {ca['qty_unit_fused']} "
            f"| {cb['unit_in_name']} | {ca['unit_in_name']} "
            f"| {(cb['split_ok']+cb['qty_only_no_unit'])/n_b:.0%} "
            f"| {(ca['split_ok']+ca['qty_only_no_unit'])/n_a:.0%} "
            f"| {pb['f1']:.3f} | {pa['f1']:.3f} |"
        )
    (args.out / "per_photo.md").write_text("\n".join(md_lines) + "\n")

    print(f"\n=== Replay: {args.runs} ===")
    print(f"{'Metric':<30} {'Before':>8} {'After':>8} {'Delta':>8}")
    print("-" * 58)
    metrics = [
        ("scale_ok_rate", "Scale-ok rate"),
        ("qty_unit_fused_rate", "qty/unit fused rate"),
        ("unit_in_name_rate", "unit-in-name rate"),
        ("ingredient_f1_mean", "Ingredient F1"),
        ("title_accuracy_mean", "Title accuracy"),
    ]
    for key, label in metrics:
        b = before[key]
        a = after[key]
        d = delta.get(key, a - b)
        print(f"{label:<30} {b:>8.3f} {a:>8.3f} {d:>+8.3f}")

    print(f"\nNormalize warnings applied: {len(all_norm_warnings)}")
    print(f"Output written to: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
