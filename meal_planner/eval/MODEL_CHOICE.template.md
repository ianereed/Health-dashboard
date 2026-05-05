# MODEL_CHOICE — Recipe Photo Extraction

> Snapshot date: <!-- fill in -->

## Decision

<!-- State the chosen model and one-sentence reason. -->

**Chosen model:** <!-- e.g. qwen2.5-vl:7b -->

**Reason:** <!-- e.g. Highest F1 among local models, p95 < 30s, no quota ceiling -->

## Scores

| Model | title_acc | F1 | parse | struct_valid | p50_s | p95_s | peak_rss_gb | rpd_headroom |
|---|---|---|---|---|---|---|---|---|
| gemini-2.5-flash | | | | | | | | |
| gemini-2.5-flash-lite | | | | | | | | |
| qwen2.5-vl:7b | | | | | | | | |
| qwen2.5-vl:3b | | | | | | | | |
| llama3.2-vision:11b | | | | | | | | |
| minicpm-v:8b | | | | | | | | |
| llama-3.2-90b-vision-preview | | | | | | | | |

**Column key:**
- `title_acc` — fraction of photos where extracted title is an exact or near-exact match (≥0.8 fuzzy)
- `F1` — bag-of-ingredients F1 with synonym normalization (precision × recall harmonic mean)
- `parse` — fraction of responses where qty+unit parsed correctly for all ingredients
- `struct_valid` — fraction of responses where output is valid JSON matching the golden schema
- `p50_s` / `p95_s` — cold-call latency in seconds (p50 and p95 across corpus)
- `peak_rss_gb` — peak RSS memory for Ollama process during bench (local models only)
- `rpd_headroom` — free-tier RPD remaining after bench (hosted models only; n/a for local)

## Why this model was chosen

<!-- 3-5 bullet points with concrete evidence from the scores table. -->

- 
- 
- 

## What was rejected and why

<!-- One bullet per model not chosen. Reference scores. -->

- **gemini-2.5-flash** — 
- **gemini-2.5-flash-lite** — 
- **qwen2.5-vl:7b** — 
- **qwen2.5-vl:3b** — 
- **llama3.2-vision:11b** — 
- **minicpm-v:8b** — 
- **llama-3.2-90b-vision-preview** — 

## Quota counter status

<!-- State whether the deferred quota counter (post-Phase 15) is blocking for Phase 16+ adoption. -->

Phase 15 does not implement a live quota counter. The `--gemini-max-calls` flag serves as a
manual stand-in. The deferred quota counter becomes blocking for Phase 16+ if the chosen
model is a Gemini hosted model.

**Status:** <!-- e.g. "Blocking for Phase 16 — chosen model is gemini-2.5-flash; quota counter required before production use" OR "Non-blocking — chosen model is local; Gemini quota counter can remain deferred" -->

## Re-run command

```bash
# Run the full bench from scratch (all models, full corpus):
python meal_planner/eval/bake_off.py run \
  --corpus meal_planner/eval/recipe_photos \
  --models qwen2.5-vl:7b,qwen2.5-vl:3b,llama3.2-vision:11b,minicpm-v:8b,gemini-2.5-flash,gemini-2.5-flash-lite \
  --gemini-max-calls 6 \
  --out meal_planner/eval/results/$(date +%Y-%m-%d)/

# Resume from last run (skips rows already in terminal status):
python meal_planner/eval/bake_off.py run \
  --corpus meal_planner/eval/recipe_photos \
  --models qwen2.5-vl:7b,qwen2.5-vl:3b,llama3.2-vision:11b,minicpm-v:8b,gemini-2.5-flash,gemini-2.5-flash-lite \
  --gemini-max-calls 6 \
  --resume-from latest
```

## Raw data

<!-- Path to the committed runs.jsonl and summary.json for this decision. -->

- `meal_planner/eval/results/<!-- date -->/summary.json`
- `meal_planner/eval/results/<!-- date -->/runs.jsonl`
- Raw provider responses: `meal_planner/eval/results/<!-- date -->/raw/` (gitignored)

## When to revisit

Revisit this decision when any of the following triggers occur:

1. A new Ollama vision model releases with claimed MMMU-Pro score > current winner's F1 by 0.10+
2. Gemini free-tier RPD for `gemini-2.5-flash` changes (check AI Studio dashboard)
3. Phase 16 recipe-photo intake goes live and latency p95 > 60s in production
4. A local model that was below the pass gate is retrained and re-published

## Autoplan review summary

_See `Mac-mini/PHASE15.md` section "Autoplan review summary" for full context._
