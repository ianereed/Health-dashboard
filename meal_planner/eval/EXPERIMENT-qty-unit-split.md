# Experiment — qty/unit split via prompt tightening

> **Status:** PLAN — not yet executed.
> **Owner:** Opus auto-mode session.
> **Decides:** whether the next chunk fixes the prompt OR pivots to a 3-pass
> orchestrator (OCR → text-to-parse → verify+commit).

## Background

Live test on 2026-05-06 (orzo risotto, recipe_id=20) showed `llama3.2-vision:11b`
emits `{"qty": "1 teaspoon", "unit": null}` for **every** numeric ingredient (7/7
in that recipe). Result: 100% of ingredients fall back to `qty_raw` with NULL
`qty_per_serving`, breaking the UI's serving-size scaling feature.

The current production prompt (`meal_planner/vision/recipe_extraction_prompt.txt`)
forbids compound qty (Chunk C) but does **not** show an explicit
fused-qty-and-unit failure case. The model is honoring some structural rules but
not the qty/unit field separation.

## Goal

Determine whether a tightened prompt — adding an explicit INCORRECT example for
fused qty/unit — gets the vision model to emit `{"qty":"1","unit":"teaspoon"}`
on the existing 12-photo eval corpus, without regressing other gates (F1, title
accuracy, structural validity).

## Hypothesis

The model's structured-output discipline is fixable in-prompt. If a single
INCORRECT/CORRECT example pair lifts the qty/unit split rate from ~0% to ≥80%
on the corpus, the 1-pass architecture is salvageable. If it lifts to 30–70%,
the model is on the edge; consider a programmatic post-split (Option 3 from the
prior comparison) before pivoting. If it lifts <30%, the 3-pass orchestrator is
justified.

## Test inputs (no new recipes required)

- **Primary corpus:** `meal_planner/eval/recipe_photos_processed/IMG_9956.jpg`
  through `IMG_9967.jpg` (12 photos), each with adjacent `*.golden.json`.
- **Live test artifact:** sidecar at
  `~/Share1/Documents/Recipes/photo-intake/_done/4593630f328b93f7.json` (orzo)
  on the mini — already proves the bug exists in production.
- **Baseline run:** `meal_planner/eval/results/2026-05-06-warm-llama32/` — F1
  0.754, title 0.909, structural 1.000. New runs must hold these floors.

## Method

### Phase 1 — Establish baseline qty/unit split rate
1. Read 5 random sidecars (or all 12 prior runs.jsonl) from the existing
   `2026-05-06-warm-llama32` results dir. Count ingredients per photo where:
   - `qty` is non-empty AND parseable as a single number/fraction (= split OK).
   - `qty` is non-empty AND contains a unit token like "cup"/"tsp" (= fused).
2. Compute split rate = OK / (OK + fused). Expected based on orzo: <10%.
3. **Output:** baseline number to beat.

### Phase 2 — Author prompt variant V1
Edit `meal_planner/vision/recipe_extraction_prompt.txt` on a fresh branch
`phase16/qty-unit-split-prompt`:

Add a new INCORRECT block specifically for qty/unit fusion:
```
INCORRECT (qty must be number-only, unit must be unit-only):
{"qty": "1 teaspoon", "unit": null, "name": "olive oil"}
{"qty": "10 ounces", "unit": null, "name": "Italian sausage"}
{"qty": "1/2 pound", "unit": null, "name": "orzo"}

CORRECT:
{"qty": "1", "unit": "teaspoon", "name": "olive oil"}
{"qty": "10", "unit": "ounce", "name": "Italian sausage"}
{"qty": "1/2", "unit": "pound", "name": "orzo"}
```

Plus one-line rule near the top:
> qty MUST be a number or fraction only ("1", "1/2", "10"). NEVER include
> the unit in qty. If the source says "1 teaspoon", emit qty="1" AND
> unit="teaspoon" — never qty="1 teaspoon" with unit=null.

### Phase 3 — Run V1 on the corpus
Use `extract_recipe_from_photo()` directly (read-only — does not touch DB).
Loop on the mini via SSH:
```bash
ssh homeserver@homeserver 'cd ~/Home-Tools && jobs/.venv/bin/python -m \
  meal_planner.eval.qty_split_runner --variant v1 --corpus processed \
  --out /tmp/qty_split_v1.jsonl'
```
The runner script will need to be written (~30 LOC). For each photo:
- Call `extract_recipe_from_photo(photo, timeout_s=500, num_ctx=4096)`.
- Dump full result to JSONL.
- Compute per-photo split metrics inline.

Wall time estimate: 12 photos × ~50s warm = ~10 min + 1 cold load ≈ 11 min.

### Phase 4 — Score
For each photo, compute:
- `n_qty_present` = count of ingredients where qty != null/empty
- `n_split_ok` = count where qty parses as number-only
- `n_fused` = count where qty contains a unit token (regex on common units)
- `split_rate` = n_split_ok / n_qty_present
- Title accuracy + ingredient F1 via the existing scoring path in
  `bake_off.py:_score_run` (re-use it; do not reinvent).

Aggregate: mean split_rate, F1, title_acc across 12 photos.

### Phase 5 — Decide
| Mean split_rate | F1 vs baseline | Action |
|---|---|---|
| ≥ 0.80 | ≥ 0.74 (no regression) | Ship V1 prompt as Chunk E. |
| 0.50–0.79 | ≥ 0.74 | Try V2 (stronger emphasis or 2-shot examples), one more cycle. |
| 0.30–0.49 | any | Add programmatic qty-splitter (Option 3) on top of best prompt. |
| < 0.30 | any | 3-pass architecture pivot is justified. Document and stop. |
| any | < 0.74 | Regression — revert prompt change, document, escalate. |

### Phase 6 — Write up
Append findings to this file under "## Results". Include:
- Per-photo split_rate table.
- Aggregate numbers vs gate.
- Decision + rationale.
- If shipping: open Chunk E branch with the prompt change + a new test in
  `test_recipe_extraction_prompt.py` covering "qty must be number-only".

## Out of scope

- Other LLM losses surfaced in the orzo run (kosher salt fused, parsley
  dropped). Track separately; not part of this experiment.
- Tag quality (title-token tagging instead of categories). Separate experiment.
- Touching production DB. The runner is read-only.
- Re-deploying the consumer. The prompt file is read at import time — local
  experiment runs use `_PROMPT_TEXT = None` cache-clear, mini production keeps
  the old prompt until Chunk E ships.
- New corpus images. Use the existing 12-photo set.

## Hard rules (auto mode)

- Branch off main: `phase16/qty-unit-split-prompt`. No commits to main.
- Do NOT modify `recipes.db` on the mini.
- Do NOT touch any plist or kickstart any agent.
- Do NOT delete or move any photo in `_done/`, `_processing/`, `photo-intake/`.
- The runner script is new code in `meal_planner/eval/`. Do not reuse the
  bake-off CLI directly — it has its own gating logic that may mask split-rate
  signal. Reuse only the scoring helpers via import.
- If the mini is busy with a real ingest task during the experiment window,
  WAIT — do not kickstart anything to clear it.
- If V1 split_rate is ambiguous (0.50–0.79), STOP and report before iterating
  to V2; don't auto-loop.

## Expected outputs

1. `meal_planner/eval/qty_split_runner.py` — new, ~50 LOC.
2. `meal_planner/eval/results/qty-split-v1/runs.jsonl` — raw extractions.
3. `meal_planner/eval/results/qty-split-v1/summary.json` — aggregates.
4. `meal_planner/vision/recipe_extraction_prompt.txt` — modified on branch.
5. This file updated with "## Results" section.
6. Chunk E branch ready for review (or a documented "do not ship, pivot to 3-pass").

## Resume-from points

- After Phase 1: have baseline number. Easy stop, easy resume.
- After Phase 3: have V1 raw output. Stop here if results need eyeballing.
- After Phase 5: decision made. Ship or pivot.

## Total expected wall time

~30–45 min: ~5 min Phase 1, ~5 min prompt edit + runner write, ~11 min run,
~5 min scoring, ~5 min write-up. Cold model loads add ≤60s once.

## Results — per-recipe tables (filled in during Phase 6)

For each of the 12 photos, emit one table in this exact shape. Align by source
position. Mark dropped golden rows as `—` in the LLM column; mark hallucinated
LLM rows as `—` in the golden column.

### Template

**Photo:** `IMG_NNNN.jpg`
**Title:** golden=`...` | LLM=`...` | match=✓/✗
**Per-recipe metrics:** split_rate=N/M (X.XX), dropped=K, hallucinated=H, F1=X.XX

| # | Golden qty/unit/name | LLM qty/unit/name | Verdict |
|---|---|---|---|
| 1 | `1` / `cup` / flour | `1` / `cup` / flour | ✓ split OK |
| 2 | `2` / `tbsp` / butter | `2 tbsp` / `null` / butter | ⚠ fused |
| 3 | `1/2` / `tsp` / salt | — | ✗ dropped |
| 4 | — | `1` / `pinch` / pepper | ✗ hallucinated |

**Verdict legend:**
- ✓ split OK — qty parses as number-only AND unit non-empty (or both empty for vague)
- ⚠ fused — qty contains a unit token; unit is null/empty
- ✗ dropped — golden has it, LLM does not
- ✗ hallucinated — LLM has it, golden does not
- ⚠ name-mismatch — qty/unit fine but name diverges meaningfully

After all 12 tables, summary row:

| Metric | Baseline (2026-05-06) | V1 result | Delta |
|---|---|---|---|
| Mean split_rate | ? | ? | ? |
| Mean F1 | 0.754 | ? | ? |
| Title accuracy | 0.909 | ? | ? |
| Structural validity | 1.000 | ? | ? |
| Total dropped | ? | ? | ? |
| Total hallucinated | ? | ? | ? |
