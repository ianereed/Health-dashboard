# Ollama Memory Budget — Mac Mini (24 GB unified RAM)

## Fixed residents

| Process | RAM (approx) |
|---|---|
| qwen3:14b @ ctx=16384 (event-aggregator text, keep_alive=-1) | ~14 GB |
| OS + dispatcher + finance-monitor + huey baseline | ~2 GB |

> Source: `event-aggregator/ARCHITECTURE.md:171-175` and `.env.example:59-61`

## Available budgets

| Scenario | Available |
|---|---|
| **Coexist** (qwen3:14b hot) | ~8 GB (24 − 14 − 2) |
| **Solo** (qwen3:14b unloaded) | ~22 GB |

Both qwen3:14b + llama3.2-vision:11b cannot be hot simultaneously (14+10+2=26 GB > 24 GB).
Workers serialize via `keep_alive=0` swap. Vision unified to `llama3.2-vision:11b` 2026-05-06
(see `event-aggregator/ARCHITECTURE.md` Section 6 for the rationale).

## Per-model num_ctx table

This table is authoritative for all bake-off bench runs. Values are set via
`_NUM_CTX_TABLE` in `bake_off.py` and resolved by `_ollama_default_ctx_for()`.

| Model | Role | num_ctx | Est. hot RAM | Coexist w/ qwen3:14b? |
|---|---|---|---|---|
| minicpm-v:8b | vision | 4096 | ~7 GB | ✓ (tight — 7+14+2=23 GB) |
| qwen2.5vl:3b | vision | 6144 | ~5 GB | ✓ |
| qwen2.5vl:7b | vision | 4096 | ~7–8 GB | ✓ (tight) |
| llama3.2-vision:11b | vision | 16384 | ~12.5 GB | ✗ solo only |
| qwen2.5:3b | text | 6144 | ~4 GB | ✓ |
| qwen2.5:7b | text | 4096 | ~7 GB | ✓ (tight) |
| llama3.1:8b | text | 4096 | ~7–8 GB | ✓ (tight) |

## Why these num_ctx values?

The default Ollama context window is 2048 tokens. Corpus recipes average ~800–1200
tokens of prompt + image encoding, but 14-ingredient recipes can exceed 2048 tokens
when the image encoding is large, causing **silent truncation** — the model silently
stops reading the recipe mid-list. This was identified as a root cause of low F1 in
the Phase 15 Round 2 bake-off (2026-05-05).

Setting `num_ctx` to 4096–6144 per model eliminates truncation for all tested recipes
while staying within the coexistence RAM budget (except llama3.2-vision:11b, which is
solo-only regardless).

### llama3.2-vision:11b raised to 16384 (2026-05-07)

Because llama3.2-vision:11b is the production vision model and is **solo-only by
design** (`keep_alive=0` swap discipline displaces qwen3:14b before any vision call),
its RAM budget is bounded by 24 GB − OS/baseline (~2 GB) = ~22 GB rather than the
~8 GB coexistence ceiling. The 4096 ctx left ~13 GB of vision-time RAM unused.

KV cache scaling for llama3.2-vision:11b (40 layers × 8 GQA heads × 128 head_dim ×
ctx × 2 bytes per KV per element):
- 4096 → ~0.7 GB KV → ~10.5 GB hot total
- 8192 → ~1.4 GB KV → ~11 GB hot total
- 16384 → ~2.7 GB KV → ~12.5 GB hot total
- 32768 → ~5.4 GB KV → ~15 GB hot total

16384 is the production default. Headroom during a vision job is ~9 GB; comfortable
margin over OS pressure. Future move to 32768 is on the table for Phase 19 (recipe
instruction extraction will lean harder on the model and may benefit from few-shot
prompting that doesn't fit in 16384).

## Bench protocol

Before any bake-off bench:
1. Verify `launchctl print gui/501/com.home-tools.jobs-consumer` is not loaded
2. Verify `/api/ps` on mini shows no other Ollama models hot
3. If qwen3:14b is resident, unload it first: `ollama generate qwen3:14b "" --keepalive 0` or restart

For multi-pass benchmarks, vision and text models must be swapped between passes — see
`bake_off_multipass.py` for the unload/swap protocol.

## Production state machine

The production 2-kind state machine lives at `jobs/lib.py:_ModelState`.

| Kind | Model | ctx | keep_alive |
|---|---|---|---|
| text | qwen3:14b | 16384 | -1 (always resident) |
| vision | llama3.2-vision:11b | 16384 | 30s (default) |

Meal-planner batch workers use a per-call keep_alive override to hold the model warm
longer during photo ingestion:

```python
@requires_model("vision", keep_alive=300, batch_hint="drain")
def meal_planner_ingest_photo(photo_path: str) -> dict:
    ...
```

Event-aggregator's one-off OCR calls omit `keep_alive` to inherit the 30s default:

```python
@requires_model("vision")
def event_aggregator_vision():
    ...
```

The `keep_alive_override` propagates through `requires_model → ensure → swap_to →
_ctx_and_keep_alive`. Existing call sites without the parameter are unaffected.
