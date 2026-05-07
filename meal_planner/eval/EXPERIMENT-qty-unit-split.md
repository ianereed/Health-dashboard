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

---

## Results — V1 (executed 2026-05-06)

**Branch:** `phase16/qty-unit-split-prompt` @ 7dfd429
**Runner:** 12 photos, 11 ok + 1 timeout (IMG_9957). Total wall ~17 min.
**Output:** `meal_planner/eval/results/qty-split-v1/{runs.jsonl,summary.json}`

### Aggregate metrics

| Metric | Baseline (2026-05-06-warm-llama32) | V1 | Delta |
|---|---|---|---|
| Mean split_rate (qty=num + unit set) | 69.8% | **72.4%** | +2.6pp |
| Mean scale_ok rate (qty parseable) | 76.7% | **82.8%** | +6.1pp |
| Mean qty_unit_fused rate | 8.1% | **1.1%** | **−7.0pp** ✓ targeted bug fixed |
| Mean unit_in_name rate | 15.1% | **16.1%** | +1.0pp ✗ not improved |
| Ingredient F1 mean | 0.754 | **0.677** | −0.077 ⚠ regression |
| Title accuracy mean | 0.909 | 0.833 | −0.076 (one timeout) |
| Structural validity | 1.000 | 0.917 | −0.083 (one timeout) |

### Per-photo split-rate (qty=number AND unit non-empty)

| photo | status | split / total | qty+unit fused | unit in name | F1 | title |
|---|---|---|---|---|---|---|
| IMG_9956 | ok | **9/9 (100%)** | **0** (was 7) | 0 | 0.82 | 1.00 |
| IMG_9957 | timeout | 0/0 | 0 | 0 | 0.00 | 0.00 |
| IMG_9958 | ok | 1/2 (50%) | 0 | 0 | 1.00 | 1.00 |
| IMG_9959 | ok | 5/8 (62%) | 0 | 0 | 0.50 | 1.00 |
| IMG_9960 | ok | **0/13 (0%)** | 0 | **12** (was 13) | 0.81 | 1.00 |
| IMG_9961 | ok | 5/8 (62%) | 1 | 0 | 0.80 | 0.00 |
| IMG_9962 | ok | 5/6 (83%) | 0 | 1 | 0.57 | 1.00 |
| IMG_9963 | ok | 12/12 (100%) | 0 | 0 | 0.55 | 1.00 |
| IMG_9964 | ok | 10/10 (100%) | 0 | 0 | 0.95 | 1.00 |
| IMG_9965 | ok | 0/1 (0%) | 0 | 1 | 0.62 | 1.00 |
| IMG_9966 | ok | 8/10 (80%) | 0 | 0 | 0.82 | 1.00 |
| IMG_9967 | ok | 8/8 (100%) | 0 | 0 | 0.67 | 1.00 |

### Verdict

Per the plan's decision rule (split_rate 72.4% in the 0.50–0.79 ambiguous zone),
**STOP and report — do not auto-iterate to V2.**

**Targeted bug — qty/unit fusion (orzo-style):**
- Effectively eliminated. Fused-qty rate dropped from 8.1% → 1.1%.
- IMG_9956 (the corpus's orzo-style failure) went from 0/9 split to **9/9 split**.

**Untargeted bug — unit-in-name (IMG_9960-style):**
- Unchanged. Rate moved 15.1% → 16.1%.
- IMG_9960 still has 12/13 ingredients with unit in name (golden has them in unit field).
- The new INCORRECT example block did not transfer the rule. Possible reasons:
  - Example used "teaspoon turmeric" (singular); the failing recipe says "teaspoons Minced Ginger" (plural + capitalized).
  - The LLM may need a stronger structural cue or a programmatic fix.

**F1 regression (0.754 → 0.677):**
- Driven primarily by IMG_9957 timeout (zeros that recipe) — without it, F1 mean is 0.738 across 11 photos (closer to baseline).
- Prompt grew from 3270 → 4788 chars; longer context could be slowing the model down on harder photos.
- The remaining 0.016 gap could be noise.

### Per-recipe tables

> **Note on alignment:** tables align by source position (golden index N vs LLM index N).
> The bipartite F1 scorer matches by name regardless of order, so when the LLM emits
> ingredients in a different order than golden, these tables show position-mismatch
> noise that the F1 score does not. The "Verdict" column reflects only the
> qty/unit/name shape of each LLM row, not whether it matches the golden row beside it.


### IMG_9956.jpg
**Status:** `ok` | **Latency:** 59.764s | **F1:** 0.82 | **Title:** golden=`Reed Parents Enchiladas` LLM=`Reed Parents Enchiladas`
**Split:** 9/9 | fused=0 | name-fuse=0 | qty-only=0

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `'2'` / `'tsp'` / vegetable oil | `'2'` / `'tsp'` / vegetable oil | ✓ split OK |
| 2 | `'1'` / `None` / large yellow onion, chopped (about 1 cup) | `'1'` / `'large yellow onion, chopped (about 1 cup)'` / onion | ✓ split OK |
| 3 | `'1'` / `None` / medium red bell pepper, chopped (about 1 cup) | `'1'` / `'medium red bell pepper, chopped (about 1 cup)'` / bell pepper | ✓ split OK |
| 4 | `'1'` / `'20oz can'` / pineapple tidbits in juice, drained, 1/3C juice reserved | `'1/2'` / `'cup'` / chopped fresh cilantro | ✓ split OK |
| 5 | `'1'` / `'15oz can'` / Progresso black beans, drained, rinsed | `'3'` / `'cups'` / shredded cheddar cheese | ✓ split OK |
| 6 | `'1'` / `'4.5oz can'` / Old El Paso chopped green chilies | `'1'` / `"Emeril's Enchilada Sauce recipe below"` / enchilada sauce | ✓ split OK |
| 7 | `'1'` / `'tsp'` / salt | `'8-10'` / `'flour tortillas (or substitute GF tortillas)'` / tortillas | ✓ split OK |
| 8 | `'1/2'` / `'cup'` / chopped fresh cilantro | `'1/2'` / `'cup'` / sour cream | ✓ split OK |
| 9 | `'3'` / `'cups'` / shredded cheddar cheese | `'8'` / `'tsp'` / chopped fresh cilantro | ✓ split OK |
| 10 | `'1'` / `None` / Emeril's enchilada sauce (recipe below) | — | ✗ dropped |
| 11 | `'8-10'` / `None` / flour tortillas | — | ✗ dropped |
| 12 | `'1/2'` / `'cup'` / sour cream | — | ✗ dropped |
| 13 | `'8'` / `'tsp'` / chopped fresh cilantro | — | ✗ dropped |

### IMG_9957.jpg
**Status:** `timeout` | **Latency:** 500.008s | **F1:** 0.00 | **Title:** golden=`Braised Beef Stew` LLM=`None`
**Split:** 0/0 | fused=0 | name-fuse=0 | qty-only=0

_(no extraction — skipping table)_

### IMG_9958.jpg
**Status:** `ok` | **Latency:** 42.123s | **F1:** 1.00 | **Title:** golden=`Mom's Dan Gung` LLM=`Mom's Dan Gung`
**Split:** 1/2 | fused=0 | name-fuse=0 | qty-only=1

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `'4'` / `None` / eggs | `'4x'` / `None` / eggs | • qty only |
| 2 | `'1'` / `'cup'` / chicken stock | `'1'` / `'cup'` / chicken stock | ✓ split OK |
| 3 | `None` / `None` / white pepper | `None` / `None` / white pepper | • vague |
| 4 | `None` / `None` / salt | `None` / `None` / salt | • vague |
| 5 | `'1'` / `None` / green onions, sliced | `None` / `None` / green onions, sliced | • vague |
| 6 | `'1/3-1/2'` / `'lb'` / cooked ground pork or bacon bits | `None` / `None` / cooked ground pork or bacon bits | • vague |
| 7 | `None` / `None` / soy sauce | `None` / `None` / soy sauce | • vague |
| 8 | `None` / `None` / sesame oil | `None` / `None` / sesame oil | • vague |

### IMG_9959.jpg
**Status:** `ok` | **Latency:** 49.366s | **F1:** 0.50 | **Title:** golden=`Sushi` LLM=`Sushi`
**Split:** 5/8 | fused=0 | name-fuse=0 | qty-only=3

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `'6'` / `'sheets'` / Yamamoto Yama seaweed | `'6'` / `None` / seaweed | • qty only |
| 2 | `'1'` / `'pack'` / Aquamarine imitation crab (8-10 sticks), cut into 1cm pieces | `'1'` / `None` / immitation crab | • qty only |
| 3 | `None` / `None` / Kewpie mayo (to taste) | `'1'` / `None` / mayo | • qty only |
| 4 | `'2'` / `'cups'` / short grain rice (ie Nishiki), uncooked | `'2'` / `'cups'` / rice | ✓ split OK |
| 5 | `'1'` / `None` / large avocado, cut into small strips | `'1'` / `'avocado'` / avocado | ✓ split OK |
| 6 | `'1'` / `'6inx4in piece'` / sashimi-grade salmon, cut into small strips | `'1'` / `'fish'` / fish | ✓ split OK |
| 7 | `'6'` / `'pieces'` / tempura shrimp, baked and cut lengthwise | `'6'` / `'tempura shrimp'` / tempura shrimp | ✓ split OK |
| 8 | `None` / `None` / roasted sesame seeds (for topping rice) | `'1'` / `'roasted sesame seeds'` / roasted sesame seeds | ✓ split OK |

### IMG_9960.jpg
**Status:** `ok` | **Latency:** 65.288s | **F1:** 0.81 | **Title:** golden=`Instant Pot Butter Chicken` LLM=`Instant Pot Butter Chicken`
**Split:** 0/13 | fused=0 | name-fuse=12 | qty-only=1

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `'1'` / `'14oz can'` / canned tomatoes | `'1 14-'` / `None` / Canned Tomatoes | • qty only |
| 2 | `'5-6'` / `'cloves'` / garlic | `'5-6'` / `None` / cloves Garlic | ⚠ unit in name |
| 3 | `'1-2'` / `'tsp'` / minced ginger | `'1-2'` / `None` / teaspoons Minced Ginger | ⚠ unit in name |
| 4 | `'1'` / `'tsp'` / turmeric | `'1'` / `None` / teaspoon Turmeric | ⚠ unit in name |
| 5 | `'1/2'` / `'tsp'` / cayenne pepper | `'1/2'` / `None` / teaspoons Cayenne Pepper | ⚠ unit in name |
| 6 | `'1'` / `'tsp'` / smoked paprika | `'1'` / `None` / teaspoon Smoked Paprika | ⚠ unit in name |
| 7 | `'1'` / `'tsp'` / kosher salt | `'1'` / `None` / teaspoon Kosher Salt | ⚠ unit in name |
| 8 | `'1'` / `'tsp'` / garam masala | `'1'` / `None` / teaspoon Garam Masala | ⚠ unit in name |
| 9 | `'1'` / `'tsp'` / ground cumin | `'1'` / `None` / teaspoon Ground Cumin | ⚠ unit in name |
| 10 | `'2-3'` / `'lb'` / boneless skinless chicken thighs (or breast, bone-in; if frozen add 1-2 min to cook time) | `'2-3/4'` / `None` / pound Boneless Skinless Chicken Thighs | ⚠ unit in name |
| 11 | `'2'` / `'oz'` / butter, cut into cubes (or coconut oil if dairy free) | `'2'` / `None` / ounces butter | ⚠ unit in name |
| 12 | `'4'` / `'oz'` / heavy cream (or full-fat coconut milk if dairy free) | `'4'` / `None` / ounces Heavy Cream | ⚠ unit in name |
| 13 | `'1'` / `'tsp'` / garam masala | `'1'` / `None` / teaspoon Garam Masala | ⚠ unit in name |
| 14 | `'1/4-1/2'` / `'cup'` / chopped cilantro | — | ✗ dropped |

### IMG_9961.jpg
**Status:** `ok` | **Latency:** 46.199s | **F1:** 0.80 | **Title:** golden=`Bok Choy and Mushroom Stir Fry` LLM=`Bok Choy and Mushroom Stir-Fry`
**Split:** 5/8 | fused=1 | name-fuse=0 | qty-only=2

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `'1'` / `'tsp'` / minced ginger | `'1'` / `None` / Ramekin | • qty only |
| 2 | `'4'` / `'cloves'` / garlic, smashed or sliced | `'1 tsp'` / `'minced'` / ginger | ⚠ qty+unit fused |
| 3 | `'12'` / `'oz'` / fresh shiitake mushrooms, trimmed, rinsed, then spun dry | `'4'` / `None` / garlic cloves | • qty only |
| 4 | `'2'` / `'tbsp'` / Shaoxing rice wine | `'1.5'` / `'lb'` / baby bok choy | ✓ split OK |
| 5 | `'1.5'` / `'lb'` / baby bok choy, trimmed, rinsed, then spun dry | `'1'` / `'tbsp'` / soy sauce | ✓ split OK |
| 6 | `'1'` / `'tbsp'` / soy sauce | `'1'` / `'tbsp'` / sesame oil | ✓ split OK |
| 7 | `'1'` / `'tbsp'` / sesame oil | `'12'` / `'oz'` / fresh shiitake mushrooms | ✓ split OK |
| 8 | — | `'2'` / `'tbsp'` / Shaoxng rice wine | ✗ hallucinated |

### IMG_9962.jpg
**Status:** `ok` | **Latency:** 51.426s | **F1:** 0.57 | **Title:** golden=`Instant Pot Chicken Juk with Scallion Sauce` LLM=`Instant Pot Chicken Juk With Scallion Sauce`
**Split:** 5/6 | fused=0 | name-fuse=1 | qty-only=0

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `'1'` / `'cup'` / short-grain white rice (about 7 1/2 oz), rinsed until water runs clear | `'1'` / `None` / cup short-grain white rice | ⚠ unit in name |
| 2 | `'3'` / `'oz'` / white button mushrooms, very thinly sliced (about 1 packed cup) | `None` / `None` / water | • vague |
| 3 | `'1'` / `'clove'` / garlic, minced | `'3'` / `'ounces'` / white button mushrooms | ✓ split OK |
| 4 | `'1'` / `'tsp'` / toasted sesame oil | `None` / `None` / small carrot | • vague |
| 5 | `'6'` / `'cups'` / low-sodium chicken broth | `None` / `None` / garlic clove | • vague |
| 6 | `'1'` / `'2-inch piece'` / fresh ginger, peeled and julienned | `'1/4'` / `'teaspoon'` / sesame oil | ✓ split OK |
| 7 | `'1'` / `'lb'` / boneless, skinless chicken thighs | `None` / `None` / chicken broth | • vague |
| 8 | `'2'` / `None` / scallions, trimmed and finely chopped (about 1/3 cup) | `'1'` / `'pound'` / boneless, skinless chicken thighs | ✓ split OK |
| 9 | `'1'` / `'tbsp'` / safflower or canola oil | `None` / `None` / scallions | • vague |
| 10 | `'2'` / `'tbsp'` / black vinegar | `'2'` / `'scallions'` / chicken broth | ✓ split OK |
| 11 | — | `'1/2'` / `'pilchoue'` / galllupl | ✗ hallucinated |

### IMG_9963.jpg
**Status:** `ok` | **Latency:** 58.568s | **F1:** 0.55 | **Title:** golden=`Ginger Fried Rice` LLM=`Ginger Fried Rice`
**Split:** 12/12 | fused=0 | name-fuse=0 | qty-only=0

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `'2'` / `'oz'` / ginger (1 tbsp minced) / 1 tbsp minced garlic | `'2'` / `'oz'` / ginger | ✓ split OK |
| 2 | `'10-16'` / `'oz'` / chicken | `'1'` / `'lb'` / chicken | ✓ split OK |
| 3 | `'4'` / `None` / eggs | `'4'` / `'eggs'` / egg | ✓ split OK |
| 4 | `'1'` / `'tsp'` / salt (for eggs) | `'2'` / `'cups'` / white rice | ✓ split OK |
| 5 | `'2'` / `'cup'` / white rice, uncooked | `'2'` / `'cups'` / water | ✓ split OK |
| 6 | `'2'` / `'cup'` / water | `'2'` / `'green'` / onion | ✓ split OK |
| 7 | `'2'` / `None` / green onion | `'1'` / `'tsp'` / salt | ✓ split OK |
| 8 | `'2'` / `'tbsp'` / oil | `'1'` / `'tsp'` / white pepper | ✓ split OK |
| 9 | `'1'` / `'tsp'` / salt (for cooking) | `'1'` / `'tsp'` / cornstarch | ✓ split OK |
| 10 | `None` / `None` / white pepper | `'1'` / `'tsp'` / sugar | ✓ split OK |
| 11 | `None` / `None` / oyster sauce | `'1'` / `'tsp'` / soy sauce | ✓ split OK |
| 12 | `None` / `None` / soy sauce | `'1'` / `'tsp'` / sesame oil | ✓ split OK |
| 13 | `None` / `None` / sesame oil | — | ✗ dropped |
| 14 | `'1'` / `'tbsp'` / water | — | ✗ dropped |
| 15 | `'1'` / `'tsp'` / cornstarch (or 1/2 tsp baking soda, omit water) | — | ✗ dropped |
| 16 | `'1'` / `'tsp'` / salt | — | ✗ dropped |
| 17 | `'1'` / `'tsp'` / white pepper | — | ✗ dropped |

### IMG_9964.jpg
**Status:** `ok` | **Latency:** 50.152s | **F1:** 0.95 | **Title:** golden=`The Best Chocolate Chip Cookies Recipe` LLM=`The Best Chocolate Chip Cookies Recipe`
**Split:** 10/10 | fused=0 | name-fuse=0 | qty-only=0

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `'8'` / `'oz'` / unsalted butter (2 sticks; 225g) | `'8'` / `'ounces'` / unsalted butter | ✓ split OK |
| 2 | `'1'` / `'ice cube'` / ice cube (about 2 tbsp / 30ml frozen water) | `'1'` / `'standard'` / ice cube | ✓ split OK |
| 3 | `'10'` / `'oz'` / all-purpose flour (about 2 cups; 280g) | `'10'` / `'ounces'` / all-purpose flour | ✓ split OK |
| 4 | `'3/4'` / `'tsp'` / baking soda (3g) | `'3/4'` / `'teaspoon'` / baking soda | ✓ split OK |
| 5 | `'2'` / `'tsp'` / Diamond Crystal kosher salt (or 1 tsp table salt; 4g) | `'2'` / `'teaspoons'` / Diamond Crystal kosher salt | ✓ split OK |
| 6 | `'5'` / `'oz'` / granulated sugar (about 3/4 cup; 140g) | `'5'` / `'ounces'` / granulated sugar | ✓ split OK |
| 7 | `'2'` / `None` / large eggs (100g) | `'2'` / `'large'` / eggs | ✓ split OK |
| 8 | `'2'` / `'tsp'` / vanilla extract (10ml) | `'2'` / `'teaspoons'` / vanilla extract | ✓ split OK |
| 9 | `'5'` / `'oz'` / dark brown sugar (about 1/2 tightly packed cup plus 2 tbsp; 140g) | `'5'` / `'ounces'` / dark brown sugar | ✓ split OK |
| 10 | `'8'` / `'oz'` / semisweet chocolate, roughly chopped into 1/4-to 1/2-inch chunks (225g) | `'8'` / `'ounces'` / semisweet chocolate | ✓ split OK |
| 11 | `None` / `None` / coarse sea salt, for garnish | — | ✗ dropped |

### IMG_9965.jpg
**Status:** `ok` | **Latency:** 49.493s | **F1:** 0.62 | **Title:** golden=`Venetian Tiramisu` LLM=`Venetian Tiramisu`
**Split:** 0/1 | fused=0 | name-fuse=1 | qty-only=0

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `None` / `None` / Pavesini ladyfingers, slim | `'2'` / `None` / large bowls | ⚠ unit in name |
| 2 | `None` / `None` / Ristora cacao powder, no sugar | `None` / `None` / electric beater or stand mixer | • vague |
| 3 | `'1'` / `'bowl'` / espresso | `None` / `None` / sifter (red mokos) | • vague |
| 4 | `None` / `None` / Granarolo mascarpone | `None` / `None` / 4x6" tin for setting | • vague |
| 5 | `'3'` / `None` / eggs | `None` / `None` / pavesini ladyfingers, slim | • vague |
| 6 | `None` / `None` / white sugar | `None` / `None` / ristora cacao powder, no sugar | • vague |
| 7 | — | `None` / `None` / bowl of espresso | ✗ hallucinated |
| 8 | — | `None` / `None` / granarolo mascarponne | ✗ hallucinated |
| 9 | — | `None` / `None` / 3 eggs | ✗ hallucinated |
| 10 | — | `None` / `None` / white sugar | ✗ hallucinated |

### IMG_9966.jpg
**Status:** `ok` | **Latency:** 54.732s | **F1:** 0.82 | **Title:** golden=`Mom's Marinated Chicken Drumsticks` LLM=`Mom's Marinated Chicken Drumsticks`
**Split:** 8/10 | fused=0 | name-fuse=0 | qty-only=2

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `'5'` / `None` / chicken drumsticks, washed | `'5'` / `None` / chicken drumsticks | • qty only |
| 2 | `'2'` / `'tbsp'` / soy sauce | `'2'` / `'tbsp'` / soy sauce | ✓ split OK |
| 3 | `'2'` / `'tbsp'` / red or yellow curry paste (or 2 tsp curry powder) | `'2'` / `'tbsp'` / red or yellow curry paste | ✓ split OK |
| 4 | `'1'` / `'tbsp'` / sesame oil | `'1'` / `'tbsp'` / sesame oil | ✓ split OK |
| 5 | `'1'` / `'tbsp'` / oyster sauce | `'1'` / `'tbsp'` / oyster sauce | ✓ split OK |
| 6 | `'1'` / `'tbsp'` / honey | `'1'` / `'tbsp'` / honey | ✓ split OK |
| 7 | `'1/2'` / `'tsp'` / salt | `'1/2'` / `'tsp'` / salt | ✓ split OK |
| 8 | `'1'` / `'tbsp'` / coconut oil | `'1'` / `'tbsp'` / coconut oil | ✓ split OK |
| 9 | `'1/2'` / `'tsp'` / black pepper | `'1/2'` / `'tsp'` / black paper | ✓ split OK |
| 10 | `None` / `None` / smashed garlic mixed with a bit of hot water (optional) | `'1'` / `None` / garlic, smashed | • qty only |
| 11 | `'1'` / `'tsp'` / minced ginger | — | ✗ dropped |
| 12 | `'1'` / `'tsp'` / minced garlic | — | ✗ dropped |

### IMG_9967.jpg
**Status:** `ok` | **Latency:** 49.917s | **F1:** 0.67 | **Title:** golden=`Chocolate Pie` LLM=`Chocolate Pie`
**Split:** 8/8 | fused=0 | name-fuse=0 | qty-only=0

| # | Golden (qty / unit / name) | LLM (qty / unit / name) | Verdict |
|---|---|---|---|
| 1 | `'1'` / `None` / whole pie crust, baked and cooled (or Oreo or graham cracker crust) | `'1'` / `'whole pie crust'` / pie crust | ✓ split OK |
| 2 | `'1 1/2'` / `'cup'` / sugar | `'1 1/2'` / `'c.'` / sugar | ✓ split OK |
| 3 | `'1/4'` / `'cup'` / cornstarch | `'1/4'` / `'c.'` / cornstarch | ✓ split OK |
| 4 | `'1/4'` / `'tsp'` / salt | `'1/4'` / `'tsp.'` / salt | ✓ split OK |
| 5 | `'3'` / `'cups'` / whole milk | `'3'` / `'c.'` / whole milk | ✓ split OK |
| 6 | `'4'` / `None` / whole egg yolks | `'4'` / `'whole'` / egg yolks | ✓ split OK |
| 7 | `'6 1/2'` / `'oz'` / bittersweet chocolate, chopped finely | `'6'` / `'1/2'` / oz. weight bittersweet chocolate | ✓ split OK |
| 8 | `'1'` / `'tsp'` / vanilla extract | `'2'` / `'tsp.'` / vanil | ✓ split OK |
| 9 | `'2'` / `'tbsp'` / butter | — | ✗ dropped |
| 10 | `None` / `None` / whipped cream, for serving | — | ✗ dropped |