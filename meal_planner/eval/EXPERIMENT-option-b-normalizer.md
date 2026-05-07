# Plan — Option B: programmatic qty/unit normalizer

> **Status:** Ready to execute autonomously in a fresh session.
> **Prereq:** Phase 16 Chunk 2.6 is on main @ `f55f8a8`; experiment branch
> `phase16/qty-unit-split-prompt` @ `ea185ad` carries the V1 prompt
> experiment results. Read `meal_planner/eval/EXPERIMENT-qty-unit-split.md`
> for the full V1 writeup before starting.

## TL;DR for the executor

Build a small post-extraction normalizer that fixes two LLM output bugs
deterministically:

1. **qty/unit fused** — `{"qty":"1 teaspoon","unit":null}` →
   `{"qty":"1","unit":"teaspoon"}`
2. **unit-in-name** — `{"qty":"1","unit":null,"name":"teaspoon turmeric"}` →
   `{"qty":"1","unit":"teaspoon","name":"turmeric"}`

Validate by replaying it over the existing `meal_planner/eval/results/2026-05-06-warm-llama32/runs.jsonl`
(production prompt baseline, 11 unique photos). If `scale_ok_rate` rises to
≥ 0.95 and F1 doesn't drop, ship to production via Chunk F. If not, stop and
report.

## Why this approach

V1 prompt experiment (see EXPERIMENT-qty-unit-split.md):
- Fixed qty/unit fusion (8.1% → 1.1%) but did not fix unit-in-name (15.1% → 16.1%).
- Caused F1 regression (0.754 → 0.677), partly from one timeout (IMG_9957).
- Decision: prompt alone won't get us to clean output. Code can.

A deterministic post-extraction step has two advantages:
- Handles BOTH bugs with one pattern matcher.
- Keeps the production prompt unchanged (no F1 regression risk).
- Reusable as the "verify pass" if we later pivot to a 3-pass orchestrator.

## Hard rules (auto mode)

- Branch off main: `phase16/option-b-normalizer`. Do NOT commit to main.
- Do NOT modify `recipes.db` on the mini.
- Do NOT touch any plist or kickstart any agent during validation.
- Do NOT delete or move any photo in `_done/`, `_processing/`, `photo-intake/`.
- Validation is read-only against existing JSONL files.
- If validation gate (Phase 4) fails → STOP. Do not ship to production.
- Production deploy at the end requires a kickstart of `com.home-tools.jobs-consumer`
  (per memory `feedback_huey_kind_module_reload`). Use `kickstart -kp`.
- If at any point a real photo lands in `photo-intake/` and triggers an
  ingest, WAIT for it to drain before kickstarting.

---

## Phase 1 — Author the normalizer (TDD)

### File: `meal_planner/vision/_normalize.py` (new)

Module surface:

```python
from typing import Any

# Conservative unit list — only real cooking measurements.
# Excludes "small/medium/large" (size adjectives, not units).
# Plural and abbreviated forms included; we lowercase but do not singularize.
_UNIT_VOCAB = frozenset({
    # volume
    "tsp", "tsp.", "teaspoon", "teaspoons",
    "tbsp", "tbsp.", "tablespoon", "tablespoons",
    "cup", "cups", "c", "c.",
    "ml", "milliliter", "milliliters",
    "l", "liter", "liters", "litre", "litres",
    "fl", "floz",  # "fl oz" handled as two tokens by the splitter
    "pint", "pints", "pt",
    "quart", "quarts", "qt",
    "gallon", "gallons", "gal",
    # mass
    "oz", "oz.", "ounce", "ounces",
    "lb", "lb.", "lbs", "lbs.", "pound", "pounds",
    "g", "gram", "grams",
    "kg", "kilogram", "kilograms",
    # count-ish
    "clove", "cloves",
    "head", "heads",
    "stick", "sticks",
    "can", "cans",
    "package", "packages", "pkg", "pkgs",
    "sprig", "sprigs",
    "bunch", "bunches",
    "slice", "slices",
    "piece", "pieces",
    "fillet", "fillets",
    "sheet", "sheets",
    "pack", "packs",
    # vague-amount tokens
    "pinch", "pinches",
    "dash", "dashes",
})


def _is_unit_token(tok: str) -> bool:
    """Case-insensitive membership in _UNIT_VOCAB."""

def normalize_ingredient(ing: dict) -> tuple[dict, list[str]]:
    """Return (normalized_dict, warnings_list).

    Two patterns, applied in order:
      1. qty/unit fused: qty matches `^<number>\s+<unit>$` and unit is empty.
         Split into qty=<number>, unit=<unit>.
      2. unit-in-name: unit is empty AND name matches `^<unit>\s+<rest>$`.
         Move the unit token to unit; name = rest.

    Both match case-insensitively but preserve original casing in the output.
    Numbers covered by pattern 1: bare digits, fractions (`1/2`), mixed
    (`1 1/2`), ranges (`5-6`, `1-2`), decimals (`2.5`).

    Returns warnings like:
      "normalize: row N qty='1 teaspoon' split → qty='1' unit='teaspoon'"
      "normalize: row N name='teaspoon turmeric' split → unit='teaspoon' name='turmeric'"

    Does NOT mutate input. Pure function.
    """

def normalize_extraction(parsed: dict) -> tuple[dict, list[str]]:
    """Apply normalize_ingredient to every entry in parsed['ingredients'].

    Returns (new_parsed, all_warnings). new_parsed has a fresh ingredients list.
    title and tags are passed through unchanged.
    If parsed is missing 'ingredients' or it's not a list, return (parsed, [])
    unchanged.
    """
```

### Tests: `meal_planner/tests/test_normalize.py` (new)

Cover at least these cases (write the tests first, then implement until green):

1. **Pattern 1 — bare digit**: `{"qty":"1 teaspoon","unit":null,"name":"olive oil"}` → qty="1", unit="teaspoon".
2. **Pattern 1 — fraction**: `{"qty":"1/2 pound","unit":null,"name":"orzo"}` → qty="1/2", unit="pound".
3. **Pattern 1 — mixed**: `{"qty":"1 1/2 cups","unit":null,"name":"sugar"}` → qty="1 1/2", unit="cups".
4. **Pattern 1 — range**: `{"qty":"5-6 cloves","unit":null,"name":"garlic"}` → qty="5-6", unit="cloves".
5. **Pattern 1 — decimal**: `{"qty":"2.5 oz","unit":null,"name":"butter"}` → qty="2.5", unit="oz".
6. **Pattern 2 — singular**: `{"qty":"1","unit":null,"name":"teaspoon turmeric"}` → unit="teaspoon", name="turmeric".
7. **Pattern 2 — plural**: `{"qty":"5-6","unit":null,"name":"cloves Garlic"}` → unit="cloves", name="Garlic".
8. **Pattern 2 — capitalized**: `{"qty":"1","unit":null,"name":"Teaspoon Turmeric"}` → unit="Teaspoon", name="Turmeric".
9. **Pattern 2 — abbreviated**: `{"qty":"2","unit":null,"name":"tsp salt"}` → unit="tsp", name="salt".
10. **No-op — unit already set**: `{"qty":"1","unit":"cup","name":"flour"}` passes through unchanged.
11. **No-op — qty null/empty**: `{"qty":null,"unit":null,"name":"salt to taste"}` passes through.
12. **No-op — name has no unit**: `{"qty":"1","unit":null,"name":"large eggs"}` passes through ("large" not in vocab).
13. **No-op — single-word name**: `{"qty":"1","unit":null,"name":"egg"}` passes through.
14. **Pattern 1 then pattern 2 don't double-fire**: after Pattern 1 splits, the name is not re-checked. Confirm with `{"qty":"1 teaspoon","unit":null,"name":"olive oil"}` — only one warning, qty="1" unit="teaspoon" name="olive oil".
15. **Pattern 2 stops at first unit token**: `{"qty":"1","unit":null,"name":"cup of cup-sized portions"}` — unit="cup", name="of cup-sized portions". Edge case is fine.
16. **`normalize_extraction` over a list**: feed the orzo recipe sidecar JSON, expect 7 warnings, all 7 ingredients normalized.

### Acceptance gate after Phase 1

```
python3 -m pytest meal_planner/tests jobs/tests -q | tail -1
```
Must show `<old_count + new_test_count> passed`. Current main is `221 passed`,
so expect `~237 passed` (16 new tests in test_normalize.py).

---

## Phase 2 — Replay validator script

### File: `meal_planner/eval/replay_normalize.py` (new)

```python
"""Replay a runs.jsonl through normalize_extraction, recompute split metrics.

Usage:
  python -m meal_planner.eval.replay_normalize \\
    --runs meal_planner/eval/results/2026-05-06-warm-llama32/runs.jsonl \\
    --corpus meal_planner/eval/recipe_photos_processed \\
    --out meal_planner/eval/results/option-b-replay-baseline/

Reads runs.jsonl, applies normalize_extraction to each `extracted` dict, writes:
  out/runs.normalized.jsonl  — same rows but normalized
  out/summary.json            — {before: {...}, after: {...}, delta: {...}}
  out/per_photo.md            — markdown table per photo: before vs after counts
"""
```

The summary should include the same metrics as `qty_split_scorer.py` (already
in repo — import its helpers if useful):
- split_rate
- scale_ok_rate
- qty_unit_fused rate
- unit_in_name rate
- ingredient F1 (use `bake_off._score`)
- title_accuracy (unchanged by normalizer; sanity check it's stable)

Run on BOTH datasets and write outputs to two dirs:

| Source runs | Output dir |
|---|---|
| `results/2026-05-06-warm-llama32/runs.jsonl` (production prompt) | `results/option-b-replay-baseline/` |
| `results/qty-split-v1/runs.jsonl` (V1 prompt) | `results/option-b-replay-v1/` |

---

## Phase 3 — Run the replay

```
python3 -m meal_planner.eval.replay_normalize \
  --runs meal_planner/eval/results/2026-05-06-warm-llama32/runs.jsonl \
  --corpus meal_planner/eval/recipe_photos_processed \
  --out meal_planner/eval/results/option-b-replay-baseline/

python3 -m meal_planner.eval.replay_normalize \
  --runs meal_planner/eval/results/qty-split-v1/runs.jsonl \
  --corpus meal_planner/eval/recipe_photos_processed \
  --out meal_planner/eval/results/option-b-replay-v1/
```

This is local-only and read-only. No mini SSH needed. Wall time: <10s each.

---

## Phase 4 — Decision gate

Read `option-b-replay-baseline/summary.json`. Compare `after` block vs `before`:

| Metric | Threshold to ship |
|---|---|
| scale_ok_rate (after) | ≥ 0.95 |
| qty_unit_fused rate (after) | ≤ 0.02 |
| unit_in_name rate (after) | ≤ 0.05 |
| ingredient F1 (after) | ≥ before – 0.02 (no real regression) |
| title_accuracy (after) | unchanged (sanity) |

**If ALL thresholds met:**
- Proceed to Phase 5 (production integration).
- Append a Results section to this file documenting the numbers.

**If ANY threshold not met:**
- STOP. Do not modify production code paths.
- Append a Results section explaining which threshold failed and the per-row
  failure cases. Hand back to user.

---

## Phase 5 — Production integration (only if Phase 4 passed)

### Integration point

Add normalize call inside `meal_planner/vision/_ollama.py:call_ollama_vision`,
right after `validate_schema(parsed)` returns valid (line ~204):

```python
is_valid, schema_errors = validate_schema(parsed)
if is_valid:
    parsed_normalized, norm_warnings = normalize_extraction(parsed)
    if norm_warnings:
        metadata["normalize_warnings"] = norm_warnings
    return parsed_normalized, metadata
```

Apply the same change in the retry path (after `parsed2` validates).

### Sidecar implications (Chunk C contract)

`jobs/kinds/meal_planner_ingest_photo.py` writes the sidecar from
`result.parsed`. After this change, `result.parsed` is post-normalize, so the
sidecar captures the normalized output, not raw LLM. **This is acceptable** —
the raw LLM text is still in `metadata.raw_response`, and the sidecar's purpose
is to diff against DB state, not to audit the model. But document it in a
comment in `meal_planner_ingest_photo.py` near the sidecar write.

### New test in `meal_planner/tests/test_extract.py`

Add a status branch test that mocks Ollama returning a fused-qty-and-unit
payload, asserts the `ExtractResult.parsed` comes back normalized AND the
`metadata` (or whatever surface — pick one) carries a normalize warning.

### Acceptance gate

```
python3 -m pytest meal_planner/tests jobs/tests -q | tail -1
```
Must show all green (target: ~239 tests).

### Squash-merge to main

```
git checkout main
git pull --ff-only origin main
git merge --squash phase16/option-b-normalizer
git commit -m "$(cat <<'EOF'
meal-planner: Phase 16 Chunk F — programmatic qty/unit normalizer

Adds meal_planner/vision/_normalize.py: deterministic post-extraction
normalizer that fixes two LLM output bugs without prompt changes:
  1. qty/unit fused ('1 teaspoon' split into qty='1', unit='teaspoon')
  2. unit-in-name ('teaspoon turmeric' split into unit, name)

Wired into call_ollama_vision after schema validation. Normalize warnings
surface via metadata['normalize_warnings'] for audit.

Validation: replayed against 2026-05-06-warm-llama32 baseline runs.jsonl;
scale_ok_rate <BEFORE>% → <AFTER>% with no F1 regression.

Acceptance gate: all tests pass.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

Replace `<BEFORE>` and `<AFTER>` with the actual numbers from
`option-b-replay-baseline/summary.json`.

### Re-run acceptance gate after squash

```
python3 -m pytest meal_planner/tests jobs/tests -q | tail -1
```
If fails: `git reset --hard origin/main` and STOP.

---

## Phase 6 — Deploy to mini

Follow the same shape as Chunk D (already journalled). Drain check + pull +
kickstart:

```bash
# Drain check (read-only)
ssh homeserver@homeserver 'sqlite3 ~/Home-Tools/meal_planner/recipes.db \
  "SELECT status, COUNT(*) FROM photos_intake GROUP BY status;"'

# If any rows are status='extracting' WAIT until they drain or move to a
# terminal state (ok / ok_partial / error / wedged). Do not kickstart while
# inflight.

# Pull
ssh homeserver@homeserver 'set -e; cd ~/Home-Tools; git fetch origin; \
  git pull --ff-only origin main; git rev-parse HEAD'
# → expect SHA equals the new main HEAD after squash. If not, STOP.

# Kickstart (-k required per feedback_launchctl_kickstart_k_flag)
ssh homeserver@homeserver 'uid=$(id -u); \
  launchctl kickstart -kp gui/${uid}/com.home-tools.jobs-consumer'

# Verify (sleep handled by you, no polling needed — just check once)
ssh homeserver@homeserver 'pgrep -fl huey_consumer | head -3; \
  tail -50 ~/Home-Tools/logs/jobs-consumer.err.log 2>/dev/null \
    | grep -iE "error|traceback|exception" | tail -10 || echo "stderr clean"'
```

---

## Phase 7 — STOP — emit handoff block

Print exactly:

```
CHUNK F HANDOFF
---
pre-merge main HEAD: <sha>
post-merge main HEAD: <sha>
mini HEAD after pull: <sha>
acceptance gate at squash commit: <N> passed
consumer pid(s) post-restart: <pid>
inflight extracting rows pre-restart: <count>
stderr.log post-restart: clean | <flagged>
replay validation:
  scale_ok before/after:        <X>% / <Y>%
  qty_unit_fused before/after:  <X>% / <Y>%
  unit_in_name before/after:    <X>% / <Y>%
  F1 before/after:              <X> / <Y>
---
Branch phase16/option-b-normalizer NOT deleted (kept until human verifies live).
```

Then STOP. Do not run any live ingest. Do not delete any branch.

Human will validate post-Chunk-F by re-dropping a recipe and confirming
qty/unit lands in correct fields.

---

## Carry-forward notes from V1 experiment

1. The orzo PDF (chocolate pot pie too) is still in `photo-intake/` undisturbed
   — scanner skips PDFs. Don't worry about it.

2. The orzo JPG already processed in production has `unit=null` for all
   ingredients (recipe_id=20). After Chunk F deploys, the row stays as-is —
   normalizer only runs on NEW extractions. A backfill is **out of scope** for
   this chunk.

3. There is also a residual "tag quality" issue (LLM emits title-tokens like
   `"easy"`, `"sausage"` instead of category tags). **Out of scope.** Track
   separately.

4. There are dropped ingredients on some photos (e.g., the parsley line on the
   orzo). **Out of scope.** Sidecar is the audit trail; recovering dropped
   rows is a different chunk.

5. IMG_9957 (Braised Beef Stew) timed out under V1's longer prompt. Production
   prompt is unchanged in this plan, so timeouts should be unaffected. If a
   replay-derived metric looks wrong, sanity-check the IMG_9957 row first.

6. Memory rules to honor:
   - `feedback_launchctl_kickstart_k_flag` — always `-kp`, never `-p` alone.
   - `feedback_huey_kind_module_reload` — restart consumer after any merge that
     touches `jobs/kinds/` or `meal_planner/vision/`.
   - `feedback_no_abstraction_for_simple_fixes` — keep _normalize.py tight; no
     unnecessary helper classes.
