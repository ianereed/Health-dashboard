"""Score qty_split_runner output: split-rate metrics + bake_off F1/title.

Reads runs.jsonl from a runner output dir, pairs each photo with its golden
JSON, computes per-photo + aggregate metrics, dumps summary.json, and prints
markdown tables for the experiment writeup.

Usage:
  python -m meal_planner.eval.qty_split_scorer \\
    --runs meal_planner/eval/results/qty-split-v1/runs.jsonl \\
    --corpus meal_planner/eval/recipe_photos_processed \\
    --out  meal_planner/eval/results/qty-split-v1/summary.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from meal_planner.eval.bake_off import _SYNONYMS_PATH, _score


_UNIT_TOKENS = (
    r"(tsp|teaspoon|teaspoons|tbsp|tablespoon|tablespoons|cup|cups|oz|ounce|ounces|"
    r"lb|lbs|pound|pounds|gram|grams|kg|ml|liter|pinch|dash|clove|cloves|stick|"
    r"sticks|can|cans|package|small|medium|large|head|heads|sprig|sprigs|bunch|"
    r"bunches|piece|pieces|slice|slices|fillet|fillets)"
)
QTY_FUSED_RE = re.compile(rf"\b{_UNIT_TOKENS}\b", re.I)
NAME_LEADS_UNIT_RE = re.compile(rf"^\s*{_UNIT_TOKENS}\b", re.I)
NUMERIC_RE = re.compile(
    r"^\s*\d+(\.\d+)?(\s*/\s*\d+)?(\s*-\s*\d+(\.\d+)?(/\d+)?)?\s*$"
    r"|^\s*\d+\s+\d+/\d+\s*$"
)


def classify_ingredient(ing: dict) -> str:
    qty = ing.get("qty")
    unit = ing.get("unit")
    name = ing.get("name", "") or ""
    if qty in (None, ""):
        return "qty_empty"
    qty_s = str(qty)
    unit_s = str(unit) if unit else ""
    if QTY_FUSED_RE.search(qty_s):
        return "qty_unit_fused"
    if NUMERIC_RE.match(qty_s) and unit_s:
        return "split_ok"
    if NUMERIC_RE.match(qty_s) and NAME_LEADS_UNIT_RE.search(name):
        return "unit_in_name"
    return "qty_only_no_unit"


def load_golden(corpus_dir: Path, photo_name: str) -> dict | None:
    base = photo_name.rsplit(".", 1)[0]
    g = corpus_dir / f"{base}.golden.json"
    if not g.exists():
        return None
    return json.loads(g.read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True, type=Path)
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    syn_doc = yaml.safe_load(_SYNONYMS_PATH.read_text())
    fractions = syn_doc.get("unicode_fractions", {})

    rows = [json.loads(l) for l in args.runs.read_text().splitlines() if l.strip()]
    per_photo = []
    agg = {
        "split_ok": 0,
        "qty_unit_fused": 0,
        "unit_in_name": 0,
        "qty_only_no_unit": 0,
        "present": 0,
    }
    f1s, titles, parses, structurals = [], [], [], []

    for r in rows:
        photo = r["photo"]
        extracted = r.get("extracted") or {}
        golden = load_golden(args.corpus, photo) or {"title": "", "ingredients": [], "tags": []}
        counts = {k: 0 for k in agg}
        ing_classes = []
        for ing in extracted.get("ingredients", []):
            c = classify_ingredient(ing)
            ing_classes.append(c)
            if c == "qty_empty":
                continue
            counts[c] += 1
            counts["present"] += 1

        if r.get("status") == "ok" and extracted:
            score = _score(extracted, golden, syn_doc, fractions)
        else:
            score = {
                "title_accuracy": 0.0,
                "ingredient_f1": 0.0,
                "parse_correctness": 0.0,
                "structural_validity": False,
                "errors": [r.get("status", "missing")],
            }

        per_photo.append(
            {
                "photo": photo,
                "status": r.get("status"),
                "latency_s": r.get("latency_s"),
                "split_counts": counts,
                "ing_classes": ing_classes,
                "extracted": extracted,
                "golden": golden,
                "score": score,
            }
        )
        for k in agg:
            agg[k] += counts[k]
        f1s.append(score["ingredient_f1"])
        titles.append(score["title_accuracy"])
        parses.append(score["parse_correctness"])
        structurals.append(1.0 if score["structural_validity"] else 0.0)

    n = max(1, agg["present"])
    summary = {
        "n_photos": len(per_photo),
        "split_rate": agg["split_ok"] / n,
        "scale_ok_rate": (agg["split_ok"] + agg["qty_only_no_unit"]) / n,
        "qty_unit_fused_rate": agg["qty_unit_fused"] / n,
        "unit_in_name_rate": agg["unit_in_name"] / n,
        "ingredients_present": agg["present"],
        "ingredient_f1_mean": sum(f1s) / max(1, len(f1s)),
        "title_accuracy_mean": sum(titles) / max(1, len(titles)),
        "parse_correctness_mean": sum(parses) / max(1, len(parses)),
        "structural_validity_mean": sum(structurals) / max(1, len(structurals)),
        "agg": agg,
        "per_photo": per_photo,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, default=str))

    print(f"\n=== Summary ({summary['n_photos']} photos) ===")
    print(f"split_ok rate (qty=num + unit set):  {summary['split_rate']:.1%}")
    print(f"scale_ok rate (qty parseable):       {summary['scale_ok_rate']:.1%}")
    print(f"qty_unit_fused rate ('1 tsp'):       {summary['qty_unit_fused_rate']:.1%}")
    print(f"unit_in_name rate ('tsp salt'):      {summary['unit_in_name_rate']:.1%}")
    print(f"\ningredient F1 mean:    {summary['ingredient_f1_mean']:.3f}")
    print(f"title accuracy mean:   {summary['title_accuracy_mean']:.3f}")
    print(f"parse correctness:     {summary['parse_correctness_mean']:.3f}")
    print(f"structural validity:   {summary['structural_validity_mean']:.3f}")

    print("\n=== Per photo ===")
    print(f"{'photo':<22} {'status':<10} {'split/total':<12} {'fused':<6} {'name-fuse':<10} {'F1':<6} {'title':<6}")
    for p in per_photo:
        c = p["split_counts"]
        total = max(1, c["present"])
        print(
            f"{p['photo']:<22} {str(p['status'] or '-'):<10} "
            f"{c['split_ok']:>2}/{c['present']:>2} ({c['split_ok']/total:.0%})  "
            f"{c['qty_unit_fused']:<6} {c['unit_in_name']:<10} "
            f"{p['score']['ingredient_f1']:.2f}   {p['score']['title_accuracy']:.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
