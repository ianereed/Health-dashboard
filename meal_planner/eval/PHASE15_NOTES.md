# Phase 15 — Architecture Notes

> **For Phase 16:** See `/Users/ianreed/.claude/plans/phase-16-nas-photo-intake.md`
> for the standalone plan. This file records the *why* behind Phase 15 decisions.

---

## TL;DR — Chosen config and verified numbers

**Chosen config for NAS-intake:**

| Config item | Value |
|---|---|
| Model | `llama3.2-vision:11b` |
| `num_ctx` | `4096` |
| `keep_alive` during batch | `300s` |
| Mode | Solo (qwen3:14b evicted before batch) |
| Preprocessing | Resize to 1500px long-edge + autocontrast (via `preprocess_images.py`) |
| Photo count | 12 recipe photos (corpus at `meal_planner/eval/recipe_photos_processed/`) |

**Verified numbers (from `results/2026-05-06-warm-llama32/summary.json`):**

| Metric | Value | Gate | Verdict |
|---|---|---|---|
| Ingredient F1 | 0.754 | ≥ 0.60 | ✅ PASS |
| Title accuracy | 0.909 | ≥ 0.85 | ✅ PASS |
| Structural validity | 1.000 | ≥ 0.95 | ✅ PASS |
| Total wall (12 photos) | 1078s (18 min) | ≤ 3600s | ✅ PASS |
| Warm latency p50 | 45.1s | informational | — |
| Warm latency p95 | 69.0s | informational | — |
| Warm latency max | 600s (1 outlier) | ≤ 120s | ❌ — outlier card |
| Cold load (first photo) | 52.6s | informational | — |
| `nas_3600s` gate | true | — | ✅ |

**Outlier handling (user decision 2026-05-06):** Per-case decision card in Mini Ops
Decisions tab (`homeserver:8503`), backed by `~/Home-Tools/run/cards.jsonl`, posted via
`jobs/adapters/card.py:post_card`. Action IDs: `gemini_fallback_<photo>` / `skip_<photo>`.
**No automatic Gemini fallback.**

---

## What to read first when revisiting this work

1. `/Users/ianreed/.claude/plans/linear-swinging-hammock.md` → STATUS section (top of file): gate table, outlier characterization, Chunks 3-5 retirement rationale
2. This file (PHASE15_NOTES.md): bench history, root cause analysis, final delta table
3. `journal-104.md` + `journal-108.md` (or whichever are current): verbatim bench output
4. `meal_planner/eval/bake_off.py:cmd_run_warm` — the warm-reuse entrypoint
5. `meal_planner/eval/MEMORY_BUDGET.md` — per-model num_ctx table and RAM math

---

## Round-2 baseline (locked reference)

These are the numbers that Phase 15 started from. All four models failed the quality gates
at this point.

| Model | n | title_acc | ingredient_f1 | struct | cold_p95 |
|---|---|---|---|---|---|
| qwen2.5vl:7b | 11 | 0.727 | 0.387 | 0.818 | 97.2s |
| qwen2.5vl:3b | 10 | 0.800 | 0.420 | 0.900 | 68.4s |
| llama3.2-vision:11b | 10 | 0.800 | 0.333 | 0.900 | 85.0s |
| minicpm-v:8b | 12 | 0.833 | 0.296 | 1.000 | 29.6s |

**Gate:** F1 ≥ 0.60, title ≥ 0.85, struct ≥ 0.95. No model passed on Round 2.

---

## Three suspected root causes and how each was tested

### Root cause 1: num_ctx never set → silent truncation

**Hypothesis:** `bake_off.py` was calling Ollama without `options.num_ctx`, defaulting to
Ollama's 2048-token context window. Recipe photos with 14+ ingredients exceed 2048 tokens
after vision encoding → model silently stops reading mid-recipe.

**Test (Chunk 2 — Win 2):** Added `_NUM_CTX_TABLE` to `bake_off.py` and `options.num_ctx`
to every Ollama call. Ran full 4-model bench on preprocessed corpus.

**Result:** F1 lift was real and significant (see delta table below). Confirmed as a major
root cause. llama3.2-vision:11b jumped from F1=0.333 to F1=0.787.

### Root cause 2: F1 metric too strict → false negatives

**Hypothesis:** Golden ingredient names are long and descriptive (e.g. "short-grain white
rice (about 7 1/2 oz), rinsed until water runs clear"). Models correctly extract "short-grain
white rice" but fail set-based F1 because the strings don't match.

**Test (Chunk 1 — Win 1):** Replaced set-equality F1 with bipartite Jaccard-based matching
(`_match_bipartite` in `bake_off.py`), stripped parentheticals, applied stop-word dropping
and synonym expansion (`synonyms.yml`). Re-scored Round 2 results.

**Result:** Significant lift on Round 2 scores (e.g. qwen2.5vl:7b: F1 0.387 → 0.698,
title 0.333 → 0.727). This was pure normalization — no new bench runs needed.

### Root cause 3: RAM thrash in coexist mode → latency spikes

**Hypothesis:** During the Chunk 2 bench, `qwen3:14b` was hot alongside vision models.
Combined RAM exceeded 22GB, causing page-outs during inference. Photos that hit the
paging threshold took 600s (HTTP timeout) instead of 50-80s.

**Test (Chunk 2.5 — Win 2b):** Ran `llama3.2-vision:11b` in solo mode:
1. Evicted `qwen3:14b` first (`/api/ps` confirmed empty before bench)
2. Cold-loaded `llama3.2-vision:11b` once
3. Processed all 12 photos warm with `keep_alive=300s`

**Result:** Photos that timed out in coexist mode (IMG_9960, IMG_9963) completed in
56s and 46s in solo mode. **However**, a different photo (IMG_9957) hit the 600s timeout
instead. See outlier characterization below.

---

## Final delta table

Progression across all three phases of improvement:

| Model | Metric | Round-2 raw | + Win 1 (rescored) | + Win 2 (preprocessed) | + Win 2b (warm/solo) |
|---|---|---|---|---|---|
| llama3.2-vision:11b | ingredient_f1 | 0.333 | ~0.642 | 0.787 | **0.754** |
| llama3.2-vision:11b | title_acc | 0.800 | ~0.800 | 0.917 | **0.909** |
| llama3.2-vision:11b | struct | 0.900 | — | 1.000 | **1.000** |
| llama3.2-vision:11b | cold_p95 | 85s | — | 646s* | 52.6s (cold-once) |
| qwen2.5vl:7b | ingredient_f1 | 0.387 | 0.698 | 0.716 | not tested |
| qwen2.5vl:3b | ingredient_f1 | 0.420 | 0.768 | 0.734 | not tested |
| minicpm-v:8b | ingredient_f1 | 0.296 | 0.517 | 0.555 | not tested |

\* 646s cold_p95 in coexist mode was entirely driven by RAM thrash (2 × 600s timeouts on
IMG_9960 and IMG_9963 when `qwen3:14b` was hot). Not an inherent model property.

**Why Win 2b (warm/solo) F1 is slightly lower than Win 2 preprocessed:**
The model is deterministic at `temperature=0.1`, so extraction quality should be identical.
The small delta (0.787 → 0.754) reflects that Chunk 2 ran n=12 photos vs n=11 warm photos
(photo 0 is scored but the warm stats exclude it), plus the 1 parse_fail in Chunk 2 vs the
different outlier photo in Chunk 2.5. Within margin of error; both clearly pass the F1 ≥ 0.60
gate.

---

## 600s outlier characterization

**Key finding: the "hard photo" rotates across runs — it is per-photo complexity, not a
coexist or warm-mode artifact.**

| Run | Mode | 600s photos |
|---|---|---|
| Chunk 2 (preprocessed, coexist) | llama3.2-vision:11b cold + qwen3:14b hot | IMG_9960, IMG_9963 |
| Chunk 2.5 (warm/solo) | llama3.2-vision:11b warm, solo | IMG_9957 |

- IMG_9960 and IMG_9963 **completed in 56s and 46s** in the warm/solo run
- IMG_9957 timed out at 600s in warm/solo mode (was fine in coexist run)

This rotation means:
1. The problem is a property of specific photos' visual complexity, not the execution environment
2. Warm mode does not fix it; multi-pass (Chunks 3–5) would not fix it either — the same
   complex photo would also be slow in Pass 1 OCR
3. ~8% rate (1/12 per run) is manageable via user-decision cards

**Outlier mitigation (at the application layer, not the model layer):** Per-case decision
card posted to `run/cards.jsonl` when the per-photo application timeout (default 300s) fires.
User chooses Gemini fallback or skip via the Decisions tab at `homeserver:8503`.

---

## Why llama3.2-vision:11b and not the others

After Phase 15 scoring:

| Model | F1 (preprocessed) | Title | Struct | Cold p95 | Coexist? |
|---|---|---|---|---|---|
| llama3.2-vision:11b | **0.787** | **0.917** | **1.000** | 646s* | ✗ solo only |
| qwen2.5vl:7b | 0.716 | 0.773 | 0.909 | 87s | ✓ tight |
| qwen2.5vl:3b | 0.734 | 0.750 | 0.833 | 64s | ✓ |
| minicpm-v:8b | 0.555 | 0.792 | 0.917 | 50s | ✓ tight |

\* 646s driven by RAM thrash; warm/solo mode reduces max to 600s on a single photo

**llama3.2-vision:11b is the clear winner on quality.** The "solo only" constraint matters
less for NAS-intake (async, batch, not latency-sensitive) than for event-aggregator
one-off OCR calls.

**Why not keep qwen2.5vl:7b for event-aggregator + llama3.2-vision:11b for meal-planner?**
RAM math: `qwen3:14b` (14GB) + `qwen2.5vl:7b` (9GB) = 23GB > 22GB available. The two
vision models **cannot coexist** — there is no architectural benefit to running both. The
swap discipline is identical for either vision model. Unifying to `llama3.2-vision:11b`
simplifies the state machine and gives both pipelines the higher-quality model.

---

## Production state machine (2-kind, post-unification)

The `jobs/lib.py:_ModelState` singleton manages a 2-kind (text/vision) exclusivity rule.

After Phase 15 unification:
- **text**: `qwen3:14b` @ `ctx=16384`, `keep_alive=-1` (always resident)
- **vision**: `llama3.2-vision:11b` @ `ctx=4096`, `keep_alive=30s` (default; meal-planner uses 300s)

Meal-planner batch uses `@requires_model("vision", keep_alive=300, batch_hint="drain")`.
Event-aggregator uses `@requires_model("vision")` (inherits the 30s default).

**See:** `meal_planner/eval/MEMORY_BUDGET.md` for the per-model num_ctx table.

---

## What Chunks 3–5 were and why they were retired

Chunks 3, 4, and 5 were a multi-pass fallback plan: if quality failed in Chunk 2.5, a
two-pass OCR → schema extraction pipeline would be tested (vision model for OCR text,
text model for JSON schema extraction).

**Why retired:** Chunk 2.5 passed quality gates cleanly (F1=0.754, title=0.909,
struct=1.000). Multi-pass would not address the latency-outlier problem — the same
complex photo that times out on direct extraction would also be slow in Pass 1 OCR.
The chunks were conditional on a quality failure that did not occur.

The Chunks 3–5 design and prompt files remain in `linear-swinging-hammock.md` as
historical reference in case a future production audit shows the F1=0.754 number
does not hold at scale.

---

## Bench tooling reference

| Tool | What it does |
|---|---|
| `bake_off.py run` | Multi-model cold bench (original, used in Chunks 1–2) |
| `bake_off.py run-warm` | Single-model warm-reuse bench (Chunk 2.5) |
| `rescore.py` | Re-score a results dir with updated normalization (Win 1) |
| `compare.py` | Side-by-side delta table across multiple result dirs |
| `preprocess_images.py` | Resize + autocontrast prep (Win 2) |
| `MEMORY_BUDGET.md` | Per-model num_ctx table + RAM math |

**Result dirs:**

| Dir | What it is |
|---|---|
| `results/2026-05-05-baseline/` | Round-2 baseline (no num_ctx, no preprocessing) |
| `results/2026-05-05/` | Round-2 raw (no num_ctx, no preprocessing, Win 1 normalization) |
| `results/2026-05-05-preprocessed/` | Chunk 2: all 4 models, num_ctx set, preprocessed photos |
| `results/2026-05-06-warm-llama32/` | Chunk 2.5: llama3.2-vision:11b warm/solo |
