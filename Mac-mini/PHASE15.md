<!-- /autoplan restore point: ~/.gstack/projects/ianereed-Home-Tools/phase14-meal-planner-v0-autoplan-restore-20260505-115823.md -->
# Phase 15 — Recipe-photo-LLM bake-off

> **Status:** APPROVED 2026-05-05 via autoplan review. Rewritten 2026-05-05 for Sonnet-auto-mode chunked execution.
> Research only. No production wiring. Output: `meal_planner/MODEL_CHOICE.md`.
>
> **Cost constraint:** $0 budget. Paid APIs (Anthropic, OpenAI) are out. Bake-off uses local Ollama + Gemini free tier (+ Groq free tier only if user already holds a key).
>
> **Quota counter:** deferred to a later phase. Phase 15 uses `--gemini-max-calls` as a manual stand-in.

## Execution model

Phase 15 runs as **6 Sonnet chunks** (C1 to C6) in fresh ~200k-context auto-mode sessions, separated by **3 human checkpoints** (HUMAN-1 to HUMAN-3) for tasks Sonnet cannot do (hand-labeling, model pulls, RPD reset wait, infra restarts). Between every Sonnet chunk and the next gate, **Opus runs the chunk's verification commands** to confirm the artifacts before unlocking the next chunk.

Each chunk is self-contained: entrance state, work items, exit artifacts, verification commands, rollback. Sonnet reads the chunk + relevant repo state and stops at the chunk boundary. Sonnet does not ask the user mid-chunk; if a step needs human judgment, it is a HUMAN-n boundary.

| Phase | Actor | Goal | Est. context |
|---|---|---|---|
| C1 | Sonnet | Scaffolding (`meal_planner/eval/` tree, `bake_off.py` skeleton, tests pass with no provider calls) | ~90k |
| HUMAN-1 | Operator | `ollama pull` 4 vision models on mini · hand-label 12 photos | ~5h wall |
| C2 | Sonnet | `_score()` rubric + `runs.jsonl` state machine + `summary.json` derivation | ~120k |
| C3 | Sonnet | Ollama vision adapter + cold-load timing + Day 0 single-photo smoke run | ~140k |
| HUMAN-2 | Operator | Disk/memory check · `launchctl bootout` shared workers for bench window | ~10 min |
| C4 | Sonnet | Full local bench: 4 Ollama models × 12 photos, summary.json with p50/p95 | ~150k |
| C5 | Sonnet | Gemini adapter (no-retry) + version capture + Day 1 6-call smoke | ~130k |
| HUMAN-3 | Operator | Wait 24h for Gemini RPD reset · AI Studio dashboard check | ~24h wall |
| C6 | Sonnet | Day 2+3 Gemini runs · render `MODEL_CHOICE.md` · update `Mac-mini/PLAN.md` | ~140k |

## Goal

Pick the recipe-photo extraction model the meal-planner will use for Phase 16+ photo intake. Replace today's `gemini-2.5-flash` default with one measured on accuracy, latency, and quota headroom against 4 local + 2 Gemini alternatives. Decide once, document why, move on.

The decision must be defensible 6 months from now. Anyone reading `MODEL_CHOICE.md` should be able to re-run the bench and either confirm the choice still holds or see what changed.

## Why now (motivation)

Phase 14.5 silently produced 0 Todoist tasks on 2026-05-04 because `gemini-2.5-flash-lite` exceeded its 20/day free-tier RPD. The quota counter that prevents recurrence is deferred to a separate phase. Phase 15 attacks the adjacent question: free-tier RPDs are the permanent ceiling under $0, so we need to know whether a local Ollama model on the mini is good enough to dodge the cap entirely.

Best outcome: a local model passes all gates and the recipe-photo path no longer touches Gemini. Worst outcome: no local passes, Gemini stays default, and the deferred quota counter becomes blocking for Phase 16+.

## Models in the bake-off

| Model | Provider | Tier | Cost | Notes |
|---|---|---|---|---|
| `gemini-2.5-flash` | Google API | free | $0 (RPD capped) | incumbent vision |
| `gemini-2.5-flash-lite` | Google API | free | $0 (20/day) | the RPD that bit us 2026-05-04 |
| `qwen2.5-vl:7b` | Ollama on mini M4 | local | $0 | local-first candidate |
| `qwen2.5-vl:3b` | Ollama on mini M4 | local | $0 | smaller/faster local |
| `llama3.2-vision:11b` | Ollama on mini M4 | local | $0 | Meta's vision model |
| `minicpm-v:8b` | Ollama on mini M4 | local | $0 | strong on benchmarks |
| `llama-3.2-90b-vision-preview` | Groq API | free | $0 (RPD capped) | optional, only if user already has Groq key |

Anthropic Haiku and OpenAI GPT-4o-mini explicitly excluded (no free API tier).

7 models × 12 photos = 84 calls full bench. Today's hard cap: **6 Gemini calls combined** across both flash variants. Bench is split across days (see C5/C6).

---

## C1 — Scaffolding

**Actor:** Sonnet auto mode. Fresh session.

### Entrance state

- On branch `phase14/meal-planner-v0` (or successor). Working tree clean.
- `meal_planner/eval/` does not exist yet (verify with `test ! -d meal_planner/eval`).
- `Mac-mini/benchmark_models.py` exists at HEAD (Sonnet will read it for the Ollama call pattern but not modify it).
- `meal_planner/consolidation.py` exists (Sonnet reads `_call_gemini` at lines 55-89 for the Gemini HTTP shape; Sonnet will NOT replicate the retry loop in lines 56-75).
- `meal_planner/.env.example` lists `GEMINI_API_KEY` (already in `.env` on the mini).

If any entrance check fails, halt with `blocked: <reason>` and do not proceed.

### Goal

Land the `meal_planner/eval/` directory tree, the `bake_off.py` argparse skeleton (no provider code yet), the seeded `synonyms.yml`, the canonical prompt file, the README, the template, and the test suite. Verify with `pytest meal_planner/eval/tests/`.

### Work items

1. Create directory `meal_planner/eval/` with `__init__.py` (empty), `tests/__init__.py` (empty).
2. Create `meal_planner/eval/recipe_photos/.gitkeep` (empty file).
3. Create `meal_planner/eval/synonyms.yml`. Seed entries (one synonym group per line, canonical name first, semicolon-separated alternates):
   - `scallion; green onion; spring onion`
   - `cilantro; coriander; coriander leaves`
   - `chickpea; garbanzo; garbanzo bean`
   - `bell pepper; capsicum; sweet pepper`
   - `eggplant; aubergine`
   - `zucchini; courgette`
   - `arugula; rocket`
   - Plus a separate top-level YAML key `unicode_fractions:` mapping `"¼": 0.25, "½": 0.5, "¾": 0.75, "⅓": 0.333, "⅔": 0.667, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875`.
4. Create `meal_planner/eval/recipe_extraction_prompt.txt`. Single canonical user prompt asking for JSON: `{title: string, ingredients: [{qty: string|null, unit: string|null, name: string}], tags: string[]}`. Instructions must explicitly state: return JSON only, no prose; `qty` is null for "to taste"/"for serving"; preserve source ingredient names (do not normalize). Length: 15-30 lines.
5. Create `meal_planner/eval/MODEL_CHOICE.template.md`. Sections per Section 7 spec below: Decision (placeholder), Scores table (empty rows for all 7 models, columns: model, title_acc, F1, parse, struct_valid, p50_s, p95_s, peak_rss_gb, rpd_headroom), Why (placeholder bullets), What was rejected (placeholder), Quota counter status (placeholder), Re-run command (filled in verbatim), Raw data (placeholder path), When to revisit (filled in mechanical triggers), Snapshot date (placeholder).
6. Create `meal_planner/eval/README.md`. Sections: corpus layout (`recipe_photos/<basename>.{png|jpg}` + sibling `<basename>.golden.json`), golden JSON schema (matches the prompt output schema), run procedure (Day 0/1/2/3 commands), supported providers (`ollama`, `gemini`, `groq`), pointer to `synonyms.yml`. Linked from `meal_planner/README.md` (append a one-line link at the bottom).
7. Create `meal_planner/eval/bake_off.py` skeleton. Top-of-file docstring matches `--help` verbatim. Imports: `argparse`, `pathlib`, `sys`, `yaml`. Argparse with two subcommands:
   - `preflight` — no flags, exits 0 with "preflight skeleton (not implemented)" stderr; in C3 this gets the real checks.
   - `run` — flags: `--corpus PATH` (required), `--models CSV` (required), `--gemini-max-calls INT` (default 0), `--resume-from STR|latest` (optional), `--out PATH` (default `meal_planner/eval/results/<today>/`), `--corpus-glob STR` (optional, for subset).
   - `run` validates each provider in `--models` against a hardcoded set `{ollama:, gemini-, llama-3.2-90b-vision-preview}` and exits non-zero on unknown provider with: `unknown provider in --models: <name>. Supported: ollama:*, gemini-*, llama-3.2-90b-vision-preview`.
   - `run` skeleton calls `_load_synonyms()` to verify yaml parses but does not call any provider.
8. Create `meal_planner/eval/tests/test_bake_off_cli.py`:
   - `test_preflight_bails_without_ollama_dir(monkeypatch)` — patches `Path.home` to a temp dir, invokes `bake_off.py preflight` via subprocess, asserts non-zero exit. (In C1 the preflight is a stub that exits 0; this test is marked `xfail` with a comment "implemented in C3" so the test file is in place but not blocking.) Actually: in C1, write the test as a passing test that verifies the stub exit message contains "preflight skeleton". C3 will replace it.
   - `test_run_rejects_unknown_provider()` — invokes `bake_off.py run --corpus /tmp --models foobar:1b`, asserts non-zero exit with stderr matching `unknown provider`.
   - `test_run_accepts_known_providers()` — invokes `bake_off.py run --corpus /tmp/nonexistent --models qwen2.5-vl:3b,gemini-2.5-flash --gemini-max-calls 0`, asserts non-zero exit but for a different reason (corpus does not exist; not an unknown-provider error).
9. Create `meal_planner/eval/tests/test_synonyms.py`:
   - `test_synonyms_loads()` — loads `synonyms.yml`, asserts `scallion` group contains `green onion`.
   - `test_unicode_fractions_loaded()` — asserts `unicode_fractions["¼"] == 0.25`.
   - `test_normalize_synonym()` — calls a `_normalize_ingredient_name()` helper in `bake_off.py` (Sonnet must add this helper in C1 as a stub that uses `synonyms.yml`); asserts `_normalize_ingredient_name("green onion")` returns `"scallion"`.
10. Update `.gitignore` (root): add `meal_planner/eval/recipe_photos/*.png`, `meal_planner/eval/recipe_photos/*.jpg`, `meal_planner/eval/recipe_photos/*.jpeg`, `meal_planner/eval/recipe_photos/*.golden.json`, `meal_planner/eval/results/*/raw/`. Do NOT gitignore `summary.json` or `runs.jsonl` (those commit).

### Exit artifacts

| Path | Content shape | Verification |
|---|---|---|
| `meal_planner/eval/__init__.py` | empty | `test -f meal_planner/eval/__init__.py` |
| `meal_planner/eval/synonyms.yml` | YAML with `scallion` and `unicode_fractions` keys | `python -c "import yaml; d=yaml.safe_load(open('meal_planner/eval/synonyms.yml')); assert 'unicode_fractions' in d"` |
| `meal_planner/eval/recipe_extraction_prompt.txt` | 15-30 lines, mentions "JSON" and "to taste" | `grep -q '"to taste"\|to taste' meal_planner/eval/recipe_extraction_prompt.txt` |
| `meal_planner/eval/bake_off.py` | argparse with `preflight` and `run` subcommands | `python meal_planner/eval/bake_off.py --help \| grep -q 'preflight'` |
| `meal_planner/eval/MODEL_CHOICE.template.md` | 9 sections per Section 7 spec | `grep -c '^##\|^###' meal_planner/eval/MODEL_CHOICE.template.md` returns ≥9 |
| `meal_planner/eval/README.md` | corpus layout + run procedure | `grep -q 'recipe_photos' meal_planner/eval/README.md` |
| `meal_planner/eval/tests/test_bake_off_cli.py` | 3 tests pass | (see verification commands) |
| `meal_planner/eval/tests/test_synonyms.py` | 3 tests pass | (see verification commands) |
| `.gitignore` | new lines for recipe_photos and results/raw | `grep -q 'meal_planner/eval/recipe_photos/.*png' .gitignore` |

### Verification commands (Opus runs)

```bash
# All from repo root.
pytest meal_planner/eval/tests/ -v
# Expect: 6 passed, 0 failed.

python meal_planner/eval/bake_off.py --help | head -20
# Expect: usage line mentioning preflight, run.

python meal_planner/eval/bake_off.py preflight 2>&1
# Expect: "preflight skeleton" mention; exit 0 in C1.

python meal_planner/eval/bake_off.py run --corpus /tmp --models foobar:1b 2>&1; echo "exit=$?"
# Expect: stderr mentions "unknown provider"; exit non-zero.

python -c "import yaml; d = yaml.safe_load(open('meal_planner/eval/synonyms.yml')); assert d['unicode_fractions']['¼'] == 0.25; print('synonyms ok')"
# Expect: "synonyms ok"

git status --short meal_planner/eval/ .gitignore
# Expect: new files staged or untracked; .gitignore modified.
```

### Rollback

If Sonnet's own self-test fails:
```bash
git checkout -- .gitignore
rm -rf meal_planner/eval/
```

### Estimated Sonnet context burn

~90k. Reads: `Mac-mini/benchmark_models.py` (skim for `_gen` shape, ~10k), `meal_planner/consolidation.py` (skim for `_call_gemini`, ~5k), this PHASE15.md (~30k), 7 file writes (~30k including pytest output). Headroom comfortable.

---

## HUMAN-1 — Pull models + hand-label corpus

**Actor:** Operator (you).

**Blocks:** C2.

### What the operator does

1. SSH to mini and pull 4 Ollama vision models. Each is 5-10GB; total ~30GB. Verify ~/.ollama has 35GB+ free first.

   ```bash
   ssh homeserver@homeserver
   df -h ~/.ollama  # confirm 35GB+ free
   ollama pull qwen2.5-vl:7b
   ollama pull qwen2.5-vl:3b
   ollama pull llama3.2-vision:11b
   ollama pull minicpm-v:8b
   ollama list
   ```

2. Drop 12 recipe photos in `meal_planner/eval/recipe_photos/` on the laptop (NOT the mini — these stay local-only). Source: 8 NYT/Bon Appetit/Serious Eats screenshots + 2 phone photos of physical cookbook pages + 2 edge cases (1 handwritten, 1 mixed-language Italian/English).

3. Hand-label each photo by creating `<basename>.golden.json` siblings matching the schema in `meal_planner/eval/README.md`:

   ```json
   {
     "title": "One-Pan Orzo With Spinach and Feta",
     "ingredients": [
       {"qty": "1", "unit": "lb", "name": "orzo"},
       {"qty": "4", "unit": "cup", "name": "vegetable broth"},
       {"qty": null, "unit": null, "name": "salt to taste"}
     ],
     "tags": ["pasta", "vegetarian", "weeknight"]
   }
   ```

   Budget: 4h total (NYT recipes have 12-18 ingredients; 10 min/photo was under-counted in initial planning).

### What Opus verifies

```bash
# On laptop, repo root:
ls meal_planner/eval/recipe_photos/*.{png,jpg,jpeg} 2>/dev/null | wc -l
# Expect: 12

ls meal_planner/eval/recipe_photos/*.golden.json | wc -l
# Expect: 12

# Validate every golden parses and has required keys.
python -c "
import json, glob, sys
ok = 0
for f in sorted(glob.glob('meal_planner/eval/recipe_photos/*.golden.json')):
    d = json.load(open(f))
    assert 'title' in d and 'ingredients' in d and 'tags' in d, f
    assert isinstance(d['ingredients'], list) and len(d['ingredients']) > 0, f
    for ing in d['ingredients']:
        assert 'qty' in ing and 'unit' in ing and 'name' in ing, f
    ok += 1
print(f'{ok}/12 goldens valid')
"
# Expect: '12/12 goldens valid'

# On mini:
ssh homeserver@homeserver 'ollama list' | grep -E 'qwen2.5-vl:7b|qwen2.5-vl:3b|llama3.2-vision:11b|minicpm-v:8b' | wc -l
# Expect: 4
```

### Expected wall time

5h (1h pulls including download wait, 4h hand-labeling).

---

## C2 — Scoring rubric + state machine

**Actor:** Sonnet auto mode. Fresh session.

### Entrance state

- C1 artifacts exist (run the C1 verification commands first; halt with `blocked: <reason>` if any fail).
- 12 photos + 12 goldens exist in `meal_planner/eval/recipe_photos/`. Verify with the HUMAN-1 verification snippet.
- `meal_planner/eval/bake_off.py` exists with the C1 skeleton.
- `meal_planner/eval/synonyms.yml` exists.

### Goal

Implement the deterministic scoring rubric (`_score(extracted, golden)`), the `runs.jsonl` append-only state machine, and the `summary.json` derivation. All testable without any model calls.

### Work items

1. In `meal_planner/eval/bake_off.py`, add `_normalize_ingredient_name(name: str, synonyms: dict) -> str`. Lowercase, strip punctuation, singularize trivially (drop trailing `s` if length > 3 and not `ss`-ending), apply synonym map (search each group; if name matches any alternate, return canonical).
2. Add `_normalize_qty(q: str|None, unicode_fractions: dict) -> str|None`:
   - `None` → `None`
   - Strip whitespace.
   - Replace each unicode fraction in `unicode_fractions` with its decimal string.
   - Range like `"2-3"` or `"2 to 3"` → keep as canonical `"2-3"` (range matches range; range matches scalar if scalar is in range).
   - Numeric: `"1"`, `"1.0"`, `"1.00"` → `"1"`.
   - "to taste", "for serving", "as needed" → `None`.
3. Add `_normalize_unit(u: str|None) -> str|None`:
   - `None` → `None`
   - Lowercase, strip period.
   - Canonical map: `cup`/`cups`/`c` → `cup`; `tablespoon`/`tablespoons`/`tbsp`/`tbs`/`T` → `tbsp`; `teaspoon`/`teaspoons`/`tsp`/`t` → `tsp`; `ounce`/`ounces`/`oz` → `oz`; `pound`/`pounds`/`lb`/`lbs` → `lb`; `gram`/`grams`/`g` → `g`; `kilogram`/`kg` → `kg`; `milliliter`/`ml` → `ml`; `liter`/`l` → `l`; else passthrough.
4. Add `_score(extracted: dict, golden: dict, synonyms: dict, unicode_fractions: dict) -> dict`. Returns `{title_accuracy: float, ingredient_f1: float, ingredient_precision: float, ingredient_recall: float, parse_correctness: float, structural_validity: bool, errors: list[str]}`.
   - Structural validity: `extracted` must be a dict with keys `title` (str), `ingredients` (list of dicts with `qty`/`unit`/`name`), `tags` (list of str). If `extracted["ingredients"]` is a string instead of a list → `structural_validity=False`, all other scores 0.0, `errors=["ingredients_not_list"]`. Other type violations: same treatment.
   - Title accuracy: `1.0` if `_casefold_strip_punct(extracted.title) == _casefold_strip_punct(golden.title)`, else `0.0`.
   - Ingredient set F1: build sets of normalized names. `precision = |E ∩ G| / |E|` (1.0 if E empty and G empty). `recall = |E ∩ G| / |G|` (handle G empty similarly). `F1 = 2*p*r/(p+r)` if `p+r > 0` else `0.0`.
   - Parse correctness: for each name in `E ∩ G`, find the corresponding qty/unit pairs (one in extracted, one in golden). `qty_match = (_normalize_qty(e.qty, ...) == _normalize_qty(g.qty, ...))`; range-vs-scalar: if either is range like `"2-3"` and the other is `"2"` or `"3"`, match. `unit_match = (_normalize_unit(e.unit) == _normalize_unit(g.unit))`. Per-ingredient `(qty_match + unit_match) / 2`. Mean across matched ingredients (0.0 if no overlap).
5. Add `_load_corpus(corpus_dir: Path) -> list[tuple[Path, dict]]`. Walks `corpus_dir`, finds every `<basename>.{png,jpg,jpeg}` with a sibling `<basename>.golden.json`, returns `[(photo_path, golden_dict)]`. Skips unmatched photos with stderr warning.
6. Add `runs.jsonl` state machine. Define `RunRow` dataclass: `schema_version: int = 1`, `model: str`, `photo: str` (basename), `status: str`, `started_at: str` (ISO), `ended_at: str|None`, `latency_s: float|None`, `cold_load_s: float|None`, `tokens_used: int|None`, `extracted: dict|None`, `error: str|None`, `score: dict|None`. Status values: `pending`, `calling`, `parsed_ok`, `parse_fail`, `provider_error`, `budget_exceeded`, `scored`. Append-only writes (open file in append mode for each row).
7. Add `_resume_from(out_dir: Path) -> set[tuple[str, str]]`. Reads `runs.jsonl`, returns set of `(model, photo_basename)` already at terminal status (`parsed_ok`, `parse_fail`, `provider_error`, `budget_exceeded`, `scored`). Refuses to resume across schema_version mismatch (raises `RuntimeError` with explicit message).
8. Add `_resolve_resume_dir(arg: str, results_root: Path) -> Path`. If `arg == "latest"`, return the most-recent dated subdir under `meal_planner/eval/results/`; if a path, use it directly; raise if neither exists.
9. Add `_summarize(out_dir: Path) -> dict`. Reads `runs.jsonl`, groups by model, computes per-model: `n_scored`, `title_accuracy_mean`, `ingredient_f1_mean`, `parse_correctness_mean`, `structural_validity_rate`, `latency_p50`, `latency_p95`, `cold_load_p50`, `cold_load_p95`, `errors` (list of (photo, error)). Writes to `<out_dir>/summary.json` with `schema_version: 1` at top level.
10. Wire `bake_off.py run` to: call `_load_corpus`, optionally `_resume_from`, iterate `(model, photo)` pairs, but DO NOT make any provider calls yet (that's C3/C5). For C2, the run command should write a `runs.jsonl` of `pending` rows for every (model, photo) pair given in `--models` and exit 0. This lets us test the state machine without provider integration.
11. Tests in `meal_planner/eval/tests/test_scoring.py`:
    - `test_perfect_match()` — synthetic extracted == golden, asserts F1 = 1.0, parse = 1.0.
    - `test_synonym_match()` — extracted uses "green onion", golden uses "scallion"; assert F1 = 1.0.
    - `test_unicode_fraction_match()` — extracted qty `"¼"`, golden qty `"0.25"`; assert qty_match.
    - `test_range_matches_scalar()` — extracted `"2-3"`, golden `"2"`; assert qty_match.
    - `test_to_taste_normalizes_to_null()` — extracted qty `"to taste"`, golden qty `None`; assert qty_match.
    - `test_ingredients_string_not_list_fails_structural()` — extracted `{"ingredients": "1 cup oil"}`; assert `structural_validity is False`.
    - `test_ingredient_f1_partial_match()` — 5 extracted, 5 golden, 3 overlap; assert F1 = 0.6.
    - `test_title_casefold()` — extracted "ONE-PAN ORZO!", golden "One-Pan Orzo"; assert title_accuracy = 1.0.
12. Tests in `meal_planner/eval/tests/test_state_machine.py`:
    - `test_resume_skips_terminal_rows(tmp_path)` — write a `runs.jsonl` with one `parsed_ok` and one `pending`; assert `_resume_from` returns only the `parsed_ok` pair.
    - `test_schema_version_mismatch_refuses(tmp_path)` — write `runs.jsonl` with `schema_version: 99`; assert `_resume_from` raises.
    - `test_summarize_aggregates(tmp_path)` — write 3 scored rows for one model; assert `summary.json` has correct means.
13. Tests in `meal_planner/eval/tests/test_corpus.py`:
    - `test_load_corpus_pairs_photos_with_goldens(tmp_path)` — create 2 photos + 1 golden; assert `_load_corpus` returns 1 pair and warns about the unpaired one.

### Exit artifacts

| Path | Content shape | Verification |
|---|---|---|
| `meal_planner/eval/bake_off.py` | adds `_score`, `_normalize_*`, `_load_corpus`, `_resume_from`, `_summarize`, `_resolve_resume_dir` | grep proves functions exist |
| `meal_planner/eval/tests/test_scoring.py` | 8 tests | pytest pass |
| `meal_planner/eval/tests/test_state_machine.py` | 3 tests | pytest pass |
| `meal_planner/eval/tests/test_corpus.py` | 1 test | pytest pass |
| `runs.jsonl` after a `--models X,Y` dry run | rows with `schema_version: 1` and `status: pending` | jq verification |

### Verification commands (Opus runs)

```bash
pytest meal_planner/eval/tests/ -v
# Expect: 18 passed (6 from C1 + 12 new), 0 failed.

grep -E '^def _(score|normalize_qty|normalize_unit|normalize_ingredient_name|load_corpus|resume_from|summarize|resolve_resume_dir)\b' meal_planner/eval/bake_off.py | wc -l
# Expect: 8

# State machine smoke (no provider calls):
TMPRUN=$(mktemp -d)
python meal_planner/eval/bake_off.py run \
  --corpus meal_planner/eval/recipe_photos/ \
  --models qwen2.5-vl:3b \
  --gemini-max-calls 0 \
  --out "$TMPRUN"
# Expect: runs.jsonl exists, all rows status=pending, schema_version=1.
jq -s '. | length' "$TMPRUN/runs.jsonl"  # if jq doesn't take jsonl directly, use: wc -l
wc -l "$TMPRUN/runs.jsonl"  # Expect: 12 (one per photo)
head -1 "$TMPRUN/runs.jsonl" | jq -r '.schema_version, .status'
# Expect: 1, pending
```

### Rollback

```bash
git checkout -- meal_planner/eval/bake_off.py
git clean -fd meal_planner/eval/tests/test_scoring.py meal_planner/eval/tests/test_state_machine.py meal_planner/eval/tests/test_corpus.py
```

### Estimated Sonnet context burn

~120k. C1 file reads (~30k), `bake_off.py` editing (~40k), 3 test files (~30k), pytest output (~20k).

---

## C3 — Ollama vision adapter + Day 0 smoke

**Actor:** Sonnet auto mode. Fresh session.

### Entrance state

- C2 artifacts exist (run C2 verification first; halt on failure).
- 12 photos + 12 goldens exist in `meal_planner/eval/recipe_photos/`.
- Mini is reachable via SSH and has `qwen2.5-vl:3b` pulled (verify: `ssh homeserver@homeserver 'ollama list' | grep qwen2.5-vl:3b`).

### Goal

Add the Ollama vision adapter, the cold-load timing path, the real preflight subcommand, and a Day 0 single-photo smoke test that proves the full call+score+persist loop works end-to-end against one real photo with one local model.

### Work items

1. In `meal_planner/eval/bake_off.py`, add `_call_ollama_vision(model: str, image_path: Path, prompt: str, base_url: str = "http://homeserver:11434") -> tuple[dict|None, dict]`. Returns `(parsed_json_or_None, metadata)`. Metadata includes `latency_s`, `cold_load_s`, `eval_count`, `raw_response` (string). Pattern follows `Mac-mini/benchmark_models.py:_gen` (lines 150-164): POST to `{base_url}/api/generate` with `format: "json"`, `images: [b64]`, `keep_alive: "10s"`, `options: {temperature: 0.1}`. Use the user prompt from `meal_planner/eval/recipe_extraction_prompt.txt` (load once, pass to function).
2. Add `_unload_ollama(model: str, base_url: str)` and `_cold_call_ollama(...)`. Force unload before every photo during the bench (Section "Cold-load latency gate" — production hits are sporadic, so cold p95 is the gate). Mirror `benchmark_models.py:_unload` (line 142) and `_cold_load` (line 243).
3. Replace the C1 `preflight` stub with the real implementation:
   - `df -h ~/.ollama` (run via SSH or locally; for the mini bench, SSH); bail if <35GB free.
   - Detect whether `com.home-tools.jobs-consumer` and `com.home-tools.dispatcher` are loaded via `launchctl print gui/501/<label>`. If yes, print exact `launchctl bootout gui/501/<label>` commands and exit non-zero. Do NOT silently bootout.
   - Read `memory_pressure` (run via SSH on mini). Bail if not "Normal".
   - Run `ollama list` (via SSH); for each model in a `--models-to-check` arg (defaults to all 4 vision models), verify a matching tag. Print `ollama pull <model>` for any missing.
   - For Gemini-related preflight: `requests.get(https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash?key=$GEMINI_API_KEY)`; record `model.version` to a stash file at `<out_dir>/gemini_versions.json`. (C5 will use this.)
   - Exit non-zero on any failure with a remediation command in stderr.
   - Add a `--ssh-host` flag (default `homeserver@homeserver`) so preflight can be run from laptop.
4. Replace the C2 stub `--models qwen2.5-vl:3b` dry run with real provider calls. The `run` command now:
   - For each `(model, photo)` pair: append `pending` row, then `calling` row, then either `parsed_ok` or `parse_fail` or `provider_error`, then `scored`.
   - Provider dispatch: `ollama:` prefix or known Ollama model names → `_call_ollama_vision`. `gemini-` prefix → `_call_gemini` (added in C5; for C3 raise NotImplementedError). `llama-3.2-90b-vision-preview` → `_call_groq` (deferred).
   - On parse fail: write raw response to `<out_dir>/raw/<photo>-<model>.txt` and reference the file in stderr.
5. Add `meal_planner/eval/tests/test_ollama_adapter.py`:
   - `test_call_ollama_vision_mocked(monkeypatch)` — mock `requests.post` to return a canned JSON response with the required schema; assert `_call_ollama_vision` returns parsed dict + correct metadata.
   - `test_call_ollama_handles_invalid_json(monkeypatch)` — mock returns non-JSON text; assert returns `(None, metadata)` and metadata captures the raw text.
   - `test_429_no_retry(monkeypatch)` — mock returns 429; assert single call (no retry loop). Comment in test references the 2026-05-04 silent failure incident.
6. Add `meal_planner/eval/tests/test_preflight.py`:
   - `test_preflight_bails_without_ollama_dir(monkeypatch)` — replace the C1 xfail stub with the real test. Mock `subprocess.run` for `df -h` to return <35GB; assert preflight exits non-zero.
   - `test_preflight_bails_when_workers_loaded(monkeypatch)` — mock `launchctl print` to return success; assert preflight exits non-zero with "bootout" in stderr.
7. Day 0 smoke test (gated behind env var `RECIPE_BAKE_OFF_LIVE=1` so CI does not hit a live Ollama):
   - Add `meal_planner/eval/tests/test_smoke_one_photo.py` with a single test that, when env var is set:
     - Picks the first photo from `meal_planner/eval/recipe_photos/`.
     - Runs `bake_off.py run --corpus <photo's parent> --models qwen2.5-vl:3b --corpus-glob <photo's basename> --out <tmpdir>`.
     - Asserts `runs.jsonl` has exactly 1 row with `status: scored` and `score.ingredient_f1 > 0.0`.
8. Add `--corpus-glob STR` flag to `run`: filters `_load_corpus` results by basename match. (Allows Day 0 single-photo smoke without rebuilding the corpus dir.)

### Exit artifacts

| Path | Content shape | Verification |
|---|---|---|
| `meal_planner/eval/bake_off.py` | adds `_call_ollama_vision`, real `preflight`, `_unload_ollama`, `--corpus-glob` | grep proves functions exist |
| `meal_planner/eval/tests/test_ollama_adapter.py` | 3 tests | pytest pass |
| `meal_planner/eval/tests/test_preflight.py` | 2 tests (replaces C1 xfail) | pytest pass |
| `meal_planner/eval/tests/test_smoke_one_photo.py` | 1 test, env-gated | pytest pass when env set |
| Smoke run output dir | `runs.jsonl` with 1 scored row, ingredient_f1 > 0 | jq verification |

### Verification commands (Opus runs)

```bash
# Test suite (mocked, no live Ollama):
pytest meal_planner/eval/tests/ -v
# Expect: 23+ passed, 0 failed (env-gated smoke test should be skipped/no-collect when env unset).

# Live smoke against the mini's Ollama:
RECIPE_BAKE_OFF_LIVE=1 pytest meal_planner/eval/tests/test_smoke_one_photo.py -v -s
# Expect: 1 passed; stdout shows real F1 score.

# Or directly:
TMPRUN=$(mktemp -d)
PHOTO_BASENAME=$(ls meal_planner/eval/recipe_photos/*.png meal_planner/eval/recipe_photos/*.jpg 2>/dev/null | head -1 | xargs basename)
python meal_planner/eval/bake_off.py run \
  --corpus meal_planner/eval/recipe_photos/ \
  --models qwen2.5-vl:3b \
  --corpus-glob "$PHOTO_BASENAME" \
  --out "$TMPRUN"
# Expect: exits 0; runs.jsonl has 1 scored row.

jq -r 'select(.status=="scored") | "\(.model) \(.photo) f1=\(.score.ingredient_f1)"' "$TMPRUN/runs.jsonl"
# Expect: one line, e.g. "qwen2.5-vl:3b orzo.png f1=0.42"

# Preflight should bail until HUMAN-2 has unloaded shared workers:
python meal_planner/eval/bake_off.py preflight 2>&1
# Expect: stderr lists bootout commands; exit non-zero. (This is correct! Operator must run them.)
```

### Rollback

```bash
git checkout -- meal_planner/eval/bake_off.py
rm -f meal_planner/eval/tests/test_ollama_adapter.py meal_planner/eval/tests/test_preflight.py meal_planner/eval/tests/test_smoke_one_photo.py
```

### Estimated Sonnet context burn

~140k. Heavy: reads `Mac-mini/benchmark_models.py` lines 142-260 (the Ollama call patterns) ~15k, edits `bake_off.py` (~50k), 3 test files (~40k), live smoke test output (~20k including any error chasing).

---

## HUMAN-2 — Bench window prep

**Actor:** Operator.

**Blocks:** C4.

### What the operator does

Before C4 fires, free up the mini for the bench window. The full local bench runs all 4 Ollama models cold-loaded between every photo (per Section "Cold-load latency gate"); shared workers competing for memory invalidate the latency measurement.

```bash
ssh homeserver@homeserver

# 1. Confirm disk.
df -h ~/.ollama
# Expect: ≥35GB free.

# 2. Confirm memory pressure.
memory_pressure | head -3
# Expect: "System-wide memory free percentage: ≥30%" or similar.

# 3. Run Sonnet's preflight (it should already be exiting non-zero with bootout commands):
~/Home-Tools/console/.venv/bin/python ~/Home-Tools/meal_planner/eval/bake_off.py preflight
# Read the stderr; copy the bootout commands.

# 4. Bootout the shared workers for the bench window.
launchctl bootout gui/501/com.home-tools.jobs-consumer
launchctl bootout gui/501/com.home-tools.dispatcher
# Capture the PIDs that just exited so we can confirm they are gone:
pgrep -f huey_consumer || echo "consumer gone"
pgrep -f dispatcher || echo "dispatcher gone"

# 5. Re-run preflight; should now exit 0.
~/Home-Tools/console/.venv/bin/python ~/Home-Tools/meal_planner/eval/bake_off.py preflight
echo "preflight exit=$?"
# Expect: 0.
```

After the full bench (after C4 and again after C5/C6), restore the workers:
```bash
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.home-tools.jobs-consumer.plist
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.home-tools.dispatcher.plist
```

### What Opus verifies

```bash
ssh homeserver@homeserver '
  ~/Home-Tools/console/.venv/bin/python ~/Home-Tools/meal_planner/eval/bake_off.py preflight
  echo "exit=$?"
'
# Expect: exit=0
```

### Expected wall time

10 minutes.

---

## C4 — Full local bench (4 models × 12 photos)

**Actor:** Sonnet auto mode. Fresh session. Runs ON the mini via SSH (not on laptop).

### Entrance state

- C3 artifacts exist (run C3 verification first; halt on failure).
- HUMAN-2 verification passes (preflight exit=0 on the mini).
- All 4 Ollama vision models pulled on mini (verify via `ssh homeserver@homeserver 'ollama list'`).

### Goal

Run the full local bench: 4 Ollama models × 12 photos = 48 calls. Each photo cold-loaded. Produce `runs.jsonl` (48 scored rows) and `summary.json` with per-model p50/p95 latency, cold-load p50/p95, F1, parse, structural-validity, peak RSS.

### Work items

1. Sonnet's first action: SSH to mini and copy the 12 photos + 12 goldens from laptop's `meal_planner/eval/recipe_photos/` to mini's `~/Home-Tools/meal_planner/eval/recipe_photos/` via `rsync`. Photos do NOT enter the repo (they are gitignored on both ends). Sonnet reads the laptop paths via `ls`, then runs `rsync -av meal_planner/eval/recipe_photos/ homeserver@homeserver:~/Home-Tools/meal_planner/eval/recipe_photos/`.
2. Run the bench command on the mini:
   ```bash
   ssh homeserver@homeserver '
     cd ~/Home-Tools
     ~/Home-Tools/console/.venv/bin/python meal_planner/eval/bake_off.py run \
       --corpus meal_planner/eval/recipe_photos/ \
       --models qwen2.5-vl:7b,qwen2.5-vl:3b,llama3.2-vision:11b,minicpm-v:8b \
       --gemini-max-calls 0 \
       --out meal_planner/eval/results/$(date +%Y-%m-%d)/
   '
   ```
3. Watch for failures during the run. Common modes: model OOM (record `provider_error: oom` and continue with next model); single-photo parse fail (record `parse_fail`, continue); RSS exceeds available memory (Sonnet halts and reports — operator may need to drop a model).
4. After the run completes, fetch results back to laptop:
   ```bash
   rsync -av homeserver@homeserver:~/Home-Tools/meal_planner/eval/results/ meal_planner/eval/results/
   ```
5. Verify locally:
   ```bash
   wc -l meal_planner/eval/results/$(date +%Y-%m-%d)/runs.jsonl
   # Expect: 96 (48 calling + 48 scored, since both are appended; or could be 144 if pending+calling+scored each appended).
   # Actual expected count depends on state machine implementation. Sonnet must document in C2 docstring.
   jq -s '[.[] | select(.status=="scored")] | length' meal_planner/eval/results/$(date +%Y-%m-%d)/runs.jsonl
   # Expect: 48
   ```
6. `summary.json` includes per-model: `n_scored: 12`, `title_accuracy_mean`, `ingredient_f1_mean`, `parse_correctness_mean`, `structural_validity_rate`, `latency_p50_warm`, `latency_p95_warm`, `cold_load_p50`, `cold_load_p95`, `peak_rss_gb`. Bench-level: `schema_version: 1`, `git_commit`, `corpus_checksum`, `ollama_model_digests` (pulled from `ollama list`), `ran_at`.
7. Sonnet's exit message reports: which models passed Section 6 hard gates (title ≥0.85, F1 ≥0.80, structural validity = 1.00, cold p95 ≤ 30s) on the local-only data so far. Does NOT yet pick a winner (Gemini comparison still pending).
8. Commit `summary.json` and `runs.jsonl` (NOT `raw/`):
   ```bash
   git add meal_planner/eval/results/$(date +%Y-%m-%d)/summary.json meal_planner/eval/results/$(date +%Y-%m-%d)/runs.jsonl
   git commit -m "phase15: local bench results $(date +%Y-%m-%d)"
   ```

### Exit artifacts

| Path | Content shape | Verification |
|---|---|---|
| `meal_planner/eval/results/<today>/runs.jsonl` | 48 scored rows, 4 models × 12 photos | jq count |
| `meal_planner/eval/results/<today>/summary.json` | per-model metrics + bench metadata, `schema_version: 1` | jq |
| `meal_planner/eval/results/<today>/raw/` | per-call request/response payloads (gitignored) | `ls` |
| `git log -1` | commit message mentions phase15 local bench | `git log -1 --oneline` |

### Verification commands (Opus runs)

```bash
TODAY=$(date +%Y-%m-%d)
DIR="meal_planner/eval/results/$TODAY"

test -f "$DIR/runs.jsonl" && echo "runs.jsonl present" || echo "MISSING"
test -f "$DIR/summary.json" && echo "summary.json present" || echo "MISSING"

jq -s '[.[] | select(.status=="scored")] | length' "$DIR/runs.jsonl"
# Expect: 48

jq '.schema_version' "$DIR/summary.json"
# Expect: 1

jq 'keys' "$DIR/summary.json"
# Expect array containing "models" or per-model keys.

jq '.models | keys' "$DIR/summary.json" 2>/dev/null || jq 'keys' "$DIR/summary.json"
# Expect 4 model names: qwen2.5-vl:7b, qwen2.5-vl:3b, llama3.2-vision:11b, minicpm-v:8b

# Check at least one model passes structural validity:
jq '.models // . | to_entries | map(select(.value.structural_validity_rate == 1.0)) | length' "$DIR/summary.json"
# Expect: ≥1

# Cold-load p95 sanity:
jq '.models // . | to_entries | map({model: .key, cold_p95: .value.cold_load_p95})' "$DIR/summary.json"
# Eyeball: each model's cold_p95 should be a positive number.
```

### Rollback

If the bench errored mid-run:
```bash
# On mini:
ssh homeserver@homeserver '
  rm -rf ~/Home-Tools/meal_planner/eval/results/$(date +%Y-%m-%d)
  launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.home-tools.jobs-consumer.plist
  launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.home-tools.dispatcher.plist
'
# Locally:
git checkout -- meal_planner/eval/results/
```

### Estimated Sonnet context burn

~150k. Bench wall time on mini: ~30-45 min (4 models × 12 photos × cold-load every time, mini M4). Sonnet polls/streams output. If a model OOMs, Sonnet halts and asks user via the HUMAN escape (boundary failure, not mid-chunk question).

---

## C5 — Gemini adapter + Day 1 6-call smoke

**Actor:** Sonnet auto mode. Fresh session.

### Entrance state

- C4 artifacts exist (run C4 verification first; halt on failure).
- `GEMINI_API_KEY` is set in `meal_planner/.env` (verify via `grep GEMINI_API_KEY meal_planner/.env | grep -v 'AIza...$'`).
- Today's Gemini RPD usage on AI Studio dashboard ≤ 14 calls combined for flash + flash-lite (operator confirms in HUMAN-2's chat — if not confirmed, defer to next day; this is captured as an entrance-state question Sonnet asks via the HUMAN-3 escape if uncertain).

### Goal

Add the Gemini vision adapter (no retry loop; explicit comment referencing the 2026-05-04 silent failure), capture model.version per call, and run the Day 1 6-call smoke: 3 photos × 2 Gemini models = exactly 6 Gemini calls. Hard stop at the 7th.

### Work items

1. In `meal_planner/eval/bake_off.py`, add `_call_gemini(model: str, image_path: Path, prompt: str, api_key: str) -> tuple[dict|None, dict]`. Pattern follows `meal_planner/consolidation.py:_call_gemini` (lines 55-89) BUT WITHOUT the retry loop in lines 56-75. Single POST to `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`. Body shape: `{"contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": <b64>}}, {"text": prompt}]}], "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}}`. On 200: extract from `candidates[0].content.parts[0].text` and parse JSON. On 429: log, return `(None, {"error": "rate_limited", "http_status": 429})` and DO NOT retry.
2. Add a code comment block above `_call_gemini` referencing the May 4 incident:
   ```python
   # NO retry loop on 429. RPD is a 24h rolling window; retries cannot recover
   # within a single bench run. The retry loop in consolidation.py:56-75 masked
   # the 2026-05-04 silent failure (4 attempts, 4 × 429, empty response, kind
   # returned []). See feedback_huey_kind_module_reload.md and the autoplan
   # review summary in PHASE15.md.
   ```
3. Add Gemini-budget enforcement to the `run` loop. Track `gemini_calls_made: int = 0`. Before each Gemini call: if `gemini_calls_made >= --gemini-max-calls`, write `budget_exceeded` row and skip. Photo selection per Gemini model: `max_calls // len(gemini_models_in_run)` photos per Gemini model, sampled deterministically by `sha1(corpus_dir)[:8]` seed (see Section "CLI flag rename" — sha1 default).
4. Add Gemini version capture. At the start of any run that includes a Gemini model: `requests.get("https://generativelanguage.googleapis.com/v1beta/models/{model}?key={api_key}")`. Record `version` field in `<out_dir>/gemini_versions.json` keyed by model. If field absent, record `version: "unspecified"` and emit a stderr warning.
5. Each Gemini-model row in `runs.jsonl` includes `gemini_model_version` field copied from the captured version.
6. Tests in `meal_planner/eval/tests/test_gemini_adapter.py`:
   - `test_call_gemini_success(monkeypatch)` — mock `requests.post` returning a canned 200 with the expected response shape; assert parsed JSON returned + metadata correct.
   - `test_call_gemini_429_no_retry(monkeypatch)` — mock returns 429; assert `requests.post` called exactly once (NOT 4 times); assert returns `(None, {error: rate_limited, http_status: 429})`. Test name explicitly references the 2026-05-04 incident in its docstring.
   - `test_gemini_budget_exhaustion(monkeypatch, tmp_path)` — `--gemini-max-calls 2`, 3 photos × 1 Gemini model; assert exactly 2 `parsed_ok` rows + 1 `budget_exceeded` row.
   - `test_gemini_version_capture(monkeypatch)` — mock `models.get` to return `{"version": "001"}`; assert `gemini_versions.json` written with `{"gemini-2.5-flash": "001"}`.
7. Run the Day 1 smoke from laptop (Gemini calls go directly from the call site, regardless of host):
   ```bash
   TODAY=$(date +%Y-%m-%d)
   python meal_planner/eval/bake_off.py run \
     --corpus meal_planner/eval/recipe_photos/ \
     --models gemini-2.5-flash,gemini-2.5-flash-lite \
     --gemini-max-calls 6 \
     --resume-from latest \
     --out "meal_planner/eval/results/$TODAY/"
   ```
   `--resume-from latest` ensures the existing `runs.jsonl` from C4 is appended to (not overwritten); only `(model, photo)` pairs not already terminal are run.
8. Verify the Gemini runs landed correctly. Expect exactly 6 new rows of `parsed_ok` or `parse_fail` or `provider_error` for Gemini models; balance of (12 photos × 2 Gemini models) − 6 = 18 rows in `budget_exceeded` status (or no rows at all for unrun pairs — depends on state machine; document choice in code).
9. Commit:
   ```bash
   git add meal_planner/eval/results/$TODAY/runs.jsonl meal_planner/eval/results/$TODAY/summary.json meal_planner/eval/results/$TODAY/gemini_versions.json
   git commit -m "phase15: gemini Day 1 smoke (6 calls) $TODAY"
   ```

### Exit artifacts

| Path | Content shape | Verification |
|---|---|---|
| `meal_planner/eval/bake_off.py` | adds `_call_gemini`, no-retry-on-429 contract, version-capture, budget-enforcement | grep + comment check |
| `meal_planner/eval/tests/test_gemini_adapter.py` | 4 tests | pytest pass |
| `meal_planner/eval/results/<today>/runs.jsonl` | now also contains 6 Gemini scored rows | jq count |
| `meal_planner/eval/results/<today>/gemini_versions.json` | `{"gemini-2.5-flash": "<v>", "gemini-2.5-flash-lite": "<v>"}` | jq |

### Verification commands (Opus runs)

```bash
TODAY=$(date +%Y-%m-%d)
DIR="meal_planner/eval/results/$TODAY"

# Test suite still green:
pytest meal_planner/eval/tests/ -v
# Expect: 27+ passed.

# Verify NO retry on 429 (look for the comment + grep for absence of retry loop):
grep -A2 "retry" meal_planner/eval/bake_off.py | grep -i "gemini" | head -5
# Eyeball: should not see a `for attempt in range(...)` loop near _call_gemini.

grep -B2 "2026-05-04" meal_planner/eval/bake_off.py
# Expect: comment block referencing the May 4 incident.

# Gemini call count (must be ≤ 6):
jq -s '[.[] | select(.model | startswith("gemini-")) | select(.status == "parsed_ok" or .status == "parse_fail" or .status == "provider_error")] | length' "$DIR/runs.jsonl"
# Expect: ≤ 6 (exactly 6 if all 6 fired).

# Budget guardrail check:
jq -s '[.[] | select(.status == "budget_exceeded")] | length' "$DIR/runs.jsonl"
# Expect: ≥ 1 (since 24 total Gemini pairs - 6 fired = 18 budget_exceeded; or implementation may not write rows for un-attempted pairs).

# Version capture:
jq '.' "$DIR/gemini_versions.json"
# Expect: 2 keys, both with non-null version strings.

# 429-no-retry test must explicitly exist:
grep -q "test_call_gemini_429_no_retry" meal_planner/eval/tests/test_gemini_adapter.py && echo "no-retry test present"
```

### Rollback

```bash
git checkout -- meal_planner/eval/bake_off.py
rm -f meal_planner/eval/tests/test_gemini_adapter.py
# Drop today's results dir if Day 1 smoke failed mid-run:
rm -rf meal_planner/eval/results/$(date +%Y-%m-%d)
```

### Estimated Sonnet context burn

~130k. Reads `consolidation.py:_call_gemini` (~5k), edits `bake_off.py` (~30k), 1 test file (~25k), live Day 1 smoke output (~30k), verification (~20k).

---

## HUMAN-3 — Wait for Gemini RPD reset

**Actor:** Operator.

**Blocks:** C6.

### What the operator does

1. Wait until midnight UTC (the Gemini free-tier RPD reset). Day 1 happened at calendar-day D; Day 2 fires at calendar-day D+1.
2. Confirm the reset on AI Studio dashboard:
   - Go to https://aistudio.google.com/app/apikey
   - Click your API key.
   - Verify "requests today" for `gemini-2.5-flash` and `gemini-2.5-flash-lite` are both reset to 0 (or near it).
3. Decision: if Day 1 local bench (C4) results already show a clear local winner that passes all Section 6 hard gates with ≥0.05 F1 cushion, **skip C6's Gemini calls entirely**. Tell Sonnet in C6's kickoff that only the MODEL_CHOICE.md render is needed; the Gemini bench is unspent budget.

### What Opus verifies

```bash
# Re-read the C4 local summary:
TODAY=$(date +%Y-%m-%d -d "yesterday" 2>/dev/null || date -v-1d +%Y-%m-%d)
DIR="meal_planner/eval/results/$TODAY"
# (Adjust date logic for actual elapsed days.)

jq '.models // . | to_entries | map(select(
    .value.title_accuracy_mean >= 0.85 and
    .value.ingredient_f1_mean >= 0.80 and
    .value.structural_validity_rate == 1.0 and
    .value.cold_load_p95 <= 30.0
)) | map(.key)' "$DIR/summary.json"
# If output is non-empty: at least one local model passes all gates.
# If the F1 cushion vs the next-best model is ≥0.05: skip Gemini in C6.
```

### Expected wall time

24 hours (mostly waiting). The dashboard check is 2 minutes.

---

## C6 — Day 2/3 Gemini + render MODEL_CHOICE.md

**Actor:** Sonnet auto mode. Fresh session.

### Entrance state

- C5 artifacts exist (run C5 verification first; halt on failure).
- HUMAN-3 verification passed (Gemini RPD reset confirmed, OR local winner already locked).
- Today's Gemini RPD usage on AI Studio is ≤ 11 (so 9 + 9 = 18 calls fit under the 20/day cap with margin).

### Goal

Run remaining Gemini calls (or skip if local won), apply Section 6 kill criteria, render `meal_planner/MODEL_CHOICE.md` from `MODEL_CHOICE.template.md` with the actual scores and chosen winner, update `Mac-mini/PLAN.md` Phase 15 entry to "DONE".

### Work items

1. **Branch path A — local won in C4:** Skip Gemini Days 2/3 entirely. Proceed to step 4.
2. **Branch path B — Gemini still in contention:** Run Day 2 (`gemini-2.5-flash` on remaining 9 photos):
   ```bash
   TODAY=$(date +%Y-%m-%d)
   python meal_planner/eval/bake_off.py run \
     --corpus meal_planner/eval/recipe_photos/ \
     --models gemini-2.5-flash \
     --gemini-max-calls 12 \
     --resume-from latest \
     --out "meal_planner/eval/results/$TODAY/"
   ```
   Verify version match: compare `gemini_versions.json` in today's run to yesterday's (Day 1) version. If different, re-run the Day 1 sample on the new version before continuing — log the discrepancy in `MODEL_CHOICE.md`'s "When to revisit" section.
3. **Branch path B continued — Day 3** (back-to-back same-day if RPD allows; otherwise next day):
   ```bash
   python meal_planner/eval/bake_off.py run \
     --corpus meal_planner/eval/recipe_photos/ \
     --models gemini-2.5-flash-lite \
     --gemini-max-calls 12 \
     --resume-from latest \
     --out "meal_planner/eval/results/$TODAY/"
   ```
4. Apply Section 6 kill criteria to `summary.json`:
   - Hard gates: title ≥0.85, F1 ≥0.80, parse correctness reported (not gated), structural validity = 1.00, cold p95 ≤ 30s.
   - Tiebreakers: local-first (≥0.10 F1 cushion before hosted preferred), then accuracy, then latency, then memory footprint.
   - Output the chosen model + the rejected models with the gate that failed.
5. Render `meal_planner/MODEL_CHOICE.md` from `meal_planner/eval/MODEL_CHOICE.template.md`:
   - Section 1 Decision: chosen model name + version pin (Gemini: from `gemini_versions.json`; Ollama: from `ollama list` digest) + key reason.
   - Section 2 Scores table: every benched model, all 4 metrics + p50/p95 cold + peak RSS (local) + RPD headroom (Gemini). Winner row bolded with `**...**`.
   - Section 3 Why: 3-5 bullets keyed to Section 6 tiebreakers.
   - Section 4 What was rejected: one line per loser with the gate that failed.
   - Section 5 Quota counter status: if a Gemini free-tier model wins, escalate the deferred quota counter phase to "must-build before Phase 16+ photo intake." If a local model wins, counter stays in normal priority for the remaining hosted call paths (categorize/consolidate still call Gemini today).
   - Section 6 Re-run command: verbatim copy of the run command (with today's `--out` path).
   - Section 7 Raw data: `meal_planner/eval/results/<dates>/`. List which days' dirs.
   - Section 8 When to revisit: mechanical triggers (date arithmetic against snapshot date; new local Ollama vision model — quarterly check at https://ollama.com/library?c=vision; quota-related production failure; $0 budget changes; ≥6 months elapsed).
   - Section 9 Snapshot date: today + Ollama digests + Gemini versions.
6. Update `Mac-mini/PLAN.md` Phase 15 entry. Find lines 380-399 (the Phase 15 stub). Replace the "Open question — API quota visibility" paragraph with: a "DONE <date>" line + one-line summary pointing at `meal_planner/MODEL_CHOICE.md` + a one-line note that the quota counter remains deferred (or is escalated, per chosen winner).
7. Run final verification: pytest still green; `MODEL_CHOICE.md` exists and names a winner that satisfies Section 6 hard gates.
8. Commit:
   ```bash
   git add meal_planner/MODEL_CHOICE.md Mac-mini/PLAN.md meal_planner/eval/results/
   git commit -m "phase15: DONE - $(grep -A1 '^## Decision' meal_planner/MODEL_CHOICE.md | tail -1 | head -c 60)"
   ```

### Exit artifacts

| Path | Content shape | Verification |
|---|---|---|
| `meal_planner/MODEL_CHOICE.md` | 9 sections, winner named, scores table, re-run command | grep |
| `Mac-mini/PLAN.md` Phase 15 entry | "DONE" status with one-line summary pointing at MODEL_CHOICE.md | grep |
| `meal_planner/eval/results/<dates>/runs.jsonl` | at most (12 photos × all benched models) scored rows | jq |
| `git log -1 --oneline` | mentions phase15: DONE | git log |

### Verification commands (Opus runs)

```bash
# pytest still green:
pytest meal_planner/eval/tests/ -v
# Expect: 27+ passed (no regressions from C2/C3/C5).

# MODEL_CHOICE.md exists and is filled in (not template):
test -f meal_planner/MODEL_CHOICE.md && echo "exists"
grep -q '^## Decision' meal_planner/MODEL_CHOICE.md && echo "decision section"
grep -q '\*\*' meal_planner/MODEL_CHOICE.md && echo "winner bolded"
grep -q 'placeholder\|TODO\|<.*>' meal_planner/MODEL_CHOICE.md && echo "WARN: placeholder text remains" || echo "no placeholders"

# Winner satisfies hard gates (mechanical check):
WINNER=$(grep -A1 '^## Decision' meal_planner/MODEL_CHOICE.md | tail -1 | grep -oE '(qwen[a-z0-9.:-]+|llama[a-z0-9.:-]+|minicpm-v:[0-9b]+|gemini-[a-z0-9.-]+)')
echo "Winner: $WINNER"
TODAY=$(date +%Y-%m-%d)
jq --arg m "$WINNER" '.models[$m] // .[$m]' meal_planner/eval/results/$TODAY/summary.json
# Eyeball: title ≥0.85, F1 ≥0.80, structural_validity_rate = 1.0, cold_load_p95 ≤30.

# PLAN.md updated:
grep -A2 '^## Phase 15' Mac-mini/PLAN.md | head -5
# Expect: "DONE" line + pointer to MODEL_CHOICE.md.

# Re-run command in MODEL_CHOICE.md is valid (parses as a real command):
grep -A5 '^## Re-run command\|^## Section 6' meal_planner/MODEL_CHOICE.md | grep 'bake_off.py run'
# Expect: a runnable command line.
```

### Rollback

```bash
git checkout -- meal_planner/MODEL_CHOICE.md Mac-mini/PLAN.md
rm -f meal_planner/MODEL_CHOICE.md
# Don't roll back results/ — those are the bench evidence.
```

### Estimated Sonnet context burn

~140k. Reads `summary.json` (~5k), template render (~30k), Day 2/3 bench output (~30k if Branch B), PLAN.md edit (~15k), verification (~25k).

---

## Models in the bake-off (full table)

(See top of file. Reproduced here for the chunks that read the bottom half.)

## Section 6 — Kill criteria / decision rule

**Hard gates** (any model failing any gate is out):
- Title accuracy ≥ 0.85 across the 12 photos
- Ingredient set F1 ≥ 0.80
- p95 latency ≤ 30s per photo, **measured cold-call** (every photo forces unload first; production hits the meal-planner sporadically and every call is effectively cold)
- Structural validity = 1.00 (all 12 photos produce parseable JSON matching schema)

**Tiebreakers** (in priority order, applied to models that pass all gates):
1. **Local-first.** Any local Ollama model that passes wins over any hosted model, even if hosted is more accurate by up to 0.10 F1. Reason: zero quota risk, zero data egress, zero "Anthropic/Google had an outage and lunch can't be planned."
2. **Accuracy.** Within local cohort (or hosted cohort if no local passes), higher F1 + parse score wins.
3. **Latency.** If accuracy ties within 0.02 F1, lower cold p95 latency wins.
4. **Memory footprint on mini.** Tied local models — pick the smaller one, leaves headroom for other Ollama users on the mini.

**"Good enough":** any model passing all gates is acceptable for production. Do not pick the "best" if it's only marginally better than "passing" — especially if better-is-hosted and passing-is-local.

**Stopping rule:** if no local model passes all gates, the bake-off elevates Gemini free-tier as the chosen path AND escalates the quota-counter from "designed" to "must-build before Phase 16+." If even Gemini free-tier fails, write the bench up as a negative result and defer Phase 16+ photo intake.

## Section 7 — `MODEL_CHOICE.md` spec

Single page. Section order locked (template at `meal_planner/eval/MODEL_CHOICE.template.md`).

1. **Decision** — one paragraph. Model name, version pin, key reason.
2. **Scores table** — all benched models, columns: title_acc, ingredient_F1, parse_correct, struct_valid, p50_cold_s, p95_cold_s, peak_rss_gb (local) / rpd_headroom (hosted). Winner row bolded.
3. **Why** — 3-5 bullets keyed to Section 6 tiebreakers.
4. **What was rejected** — one line per loser with the gate that failed.
5. **Quota counter status** — deferred to a separate phase. If a Gemini free-tier model wins, escalate to "must-build before Phase 16+ photo intake."
6. **Re-run command** — verbatim copy of the bench command for today.
7. **Raw data** — paths to `meal_planner/eval/results/<YYYY-MM-DD>/`. `summary.json` + `runs.jsonl` committed; `raw/` gitignored.
8. **When to revisit** — mechanical triggers: ≥6 months elapsed (date arithmetic); new local Ollama vision model lands (quarterly check of https://ollama.com/library?c=vision); quota-related production failure recurs; $0 budget constraint changes.
9. **Snapshot date** — today + Ollama model digests + Gemini model versions.

## Section 8 — Out of scope

- Production wiring of chosen model into `meal_planner_send_to_todoist` or any kind. That's Phase 16+.
- Quota counter design AND build. Both deferred per autoplan premise gate.
- Migrating existing 16 recipes through new model. Reseed when needed.
- UI rebuild on Recipes tab. Sidebar quota display is Phase 16+.
- Handwritten recipe extraction beyond the 1 probe photo. Per memory, out of scope.
- Multi-photo / video / step-by-step instruction extraction. Title + ingredients only.

## Done definition

1. `meal_planner/MODEL_CHOICE.md` exists and lists chosen model with scores, rationale, re-run command.
2. `meal_planner/eval/bake_off.py` is committed and reproducible.
3. `MODEL_CHOICE.md` references `meal_planner/eval/results/<dates>/` for raw evidence.
4. `Mac-mini/PLAN.md` Phase 15 entry updated to "DONE" with one-line summary pointing at `MODEL_CHOICE.md`.
5. If a Gemini free-tier model wins, deferred quota counter phase is escalated to "must-build before Phase 16+ photo intake." If a local model wins, counter stays normal-priority for remaining hosted call paths.

Phase 15 closes when the user reads `MODEL_CHOICE.md` and agrees with the choice. The decision is the deliverable, not the bench code.

---

## Autoplan review summary (2026-05-05) — historical record

Codex unavailable on this machine; reviewers were Claude subagents only (`[subagent-only]` mode per autoplan degradation matrix). Phase 2 (Design) skipped — UI hits in the plan were all false positives once quota counter UI was deferred.

### Phase outcomes

| Phase | Outcome | Findings |
|---|---|---|
| CEO | Premise gate raised; user chose to proceed with bake-off and defer quota counter | 7 findings, 1 reframe accepted (deferred counter), 6 acknowledged |
| Design | Skipped — no real UI scope after quota counter deferred | n/a |
| Eng | Approve with changes; safeguards folded into chunks | 14 findings (2 critical, 4 high, 6 medium, 4 low) |
| DX | Approve with changes; DX safeguards folded into chunks | 8 findings (1 critical, 5 high, 1 medium, 1 low) |

### Cross-phase themes (flagged by 2+ reviewers independently)

- **Reproducibility weakness.** Eng flagged Day-1-to-Day-3 schema drift; DX flagged volatile `/tmp` paths. Both addressed via `schema_version` field + `meal_planner/eval/results/<date>/` as canonical path with `summary.json` + `runs.jsonl` committed.
- **"Add a model later" oversimplification.** Eng said adapter shape doesn't collapse cleanly across providers (3 distinct request formats, 3 distinct JSON-mode mechanisms); DX said the 2-step claim hid 6+ real edit sites. Both addressed via the 7-item add-a-model checklist documented in `eval/README.md` (created in C1).
- **Prompt parity vs provider-specific structured-output mechanisms.** Eng raised it directly; DX raised it as documentation findability. Both addressed: `eval/recipe_extraction_prompt.txt` is the canonical user prompt (created in C1), structured-output mode varies per provider necessity, exact request payloads saved per call to `<out_dir>/raw/<photo>-<model>.json` for audit.

### Auto-decided (mechanical fixes — folded into chunks)

Schema lock (C1, C2); synonyms.yml (C1); single canonical prompt (C1); no-retry-on-429 with code comment (C5); runs.jsonl state machine (C2); cold-load latency gate (C3, C4); preflight subcommand not manual checklist (C3); Gemini model version capture (C5); hand-labeling budget bumped 2h → 4h (HUMAN-1); ingredient parse edge cases (C2); SDK = `requests` matching `consolidation.py` (C5); effort revised 11h → 14-15h; `/tmp` → `meal_planner/eval/results/<date>/` everywhere; CLI flag rename to `--gemini-max-calls` + `--resume-from` (C1); sha1-based seed default (C5); error message contracts with next-action copy (C3, C5); `eval/README.md` + `MODEL_CHOICE.template.md` + top-of-file docstring (C1); "when to revisit" mechanical triggers (C6); 7-item add-a-model checklist (in C1's `eval/README.md`).

### Taste decisions accepted as-is at 2026-05-05 final gate

1. Statistical thinness of n=12 — F1 noise floor (~±0.10-0.15) wider than 0.02 tiebreaker margin; tie band kept at 0.02 pending evidence it matters.
2. Local-first 0.10 F1 cushion — kept auto-applied as Section 6 tiebreaker.
3. Gemini non-determinism — accepted (no N=3 variance bounds; would blow today's 6-call cap).
4. Bench-lib refactor — accepted ~80 lines duplicated low-level Ollama plumbing in `bake_off.py` (research code, throwaway risk).
5. Local-first preference itself — kept.
6. "Decide once, move on" framing — kept.

### Deferred to TODOS.md

- Quota counter implementation (per premise gate decision).
- Phase entry-gate suggestion: "≥5 user-added recipes via real photo intake before Phase 15 starts" — CEO recommended, not accepted, not blocking.
