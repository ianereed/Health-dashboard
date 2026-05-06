# Phase 16 — meal_planner/vision/ design notes

This module is the production extraction path for NAS-dropped recipe photos. It
exists separately from `meal_planner/eval/` so the bake-off (research) and worker
(production) code paths don't drift. Plan: `~/.claude/plans/phase-16-nas-photo-intake.md`.

## Why we extracted from `eval/`

The Phase 15 plan explicitly says: "Reuse (don't re-export from `eval/`)" for the
production path. The Ollama adapter, schema validator, and prompt loader started
out as private (`_`-prefixed) helpers inside `eval/bake_off.py` because they
existed solely to drive the bench. Phase 16 productionizes them:

- `_ollama.py` now owns `call_ollama_vision`, `unload_ollama`, `default_ctx_for`,
  `validate_schema`, `load_prompt`, `cold_call_ollama`, and the `NUM_CTX_TABLE`
  constant. The prompt file `recipe_extraction_prompt.txt` moved here too.
- `eval/bake_off.py` re-imports them at module top with the original
  `_`-prefixed names so the CLI, tests, and the locked Phase 15 bench stay
  bit-for-bit identical.

The acceptance gate (re-run `bake_off.py run-warm --model llama3.2-vision:11b` on
the mini and verify F1 within ±0.02 of the locked 0.754 baseline) catches any
silent behavior drift in the extracted code paths.

## The 500s vs 600s timeout layering

`call_ollama_vision` accepts a `timeout_s` parameter (default 600s — historical
bench socket timeout). Chunk 3 will pass `timeout_s=500` from the NAS-intake
worker so a single photo can't tie up the worker thread for the full 10 minutes
the bench tolerated. The 500s number is the Phase 15 outlier policy:

> ~8% of photos hit the 600s HTTP timeout; the problematic photo rotates across
> runs. Mitigation: 500s per-photo cap → post a decision card → user picks
> Gemini-fallback or skip.

Both numbers go on the same wire (`requests.post(..., timeout=timeout_s)`) — the
distinction is purely about which call site sets it.

## Concurrency tradeoff (single huey worker, FIFO model swaps)

`@requires_model("vision", keep_alive=300, batch_hint="drain")` on the worker
means meal-planner photo-intake and event-aggregator vision share the FIFO
queue on the single huey thread. `_batch_kinds` defers opposite-kind swaps but
holds vision warm with `keep_alive=300` for the whole drain.

Worst case: if 12 photos drop while event-aggregator vision is mid-flight, the
event-aggregator OCR for medical / personal docs waits ~18 minutes (12 × ~90s
warm latency) before its swap fires. Per memory, event-aggregator vision fires
<1×/day, so the practical impact is small. We accept the tradeoff; preemption
would defeat warm-reuse, and warm-reuse is what gets the F1 + latency we need.

If event-agg traffic ever rises (e.g., a new connector lights up vision), revisit
this decision — the single-thread FIFO is the bottleneck, not any per-kind logic.
