# Phase 18 Post-Merge Review Fixups

**Status:** Ready for autonomous execution.
**Mode:** Sonnet executes start-to-finish in auto mode. Opus review agent runs at the end.
**Branch:** Create `fix/phase18-review-fixups` off `main`.
**Estimated diff:** ~120 LOC code + ~95 LOC tests, single commit.

---

## Context

A full Opus review of Phase 18 (commits `43b1beb..759cf4c`, all 5 chunks B1+B2+A1+A2+A3) ran on 2026-05-08. Critical pass found nothing. 7 mechanical issues were already auto-fixed and will already be uncommitted in the working tree when this plan runs (or already committed — check `git status` first; if clean, the auto-fixes are already in `main` via a prior commit and you should rebase from there).

Three findings remain that need real changes. This plan fixes all three in one commit.

The findings:

1. **`update_ingredient(qty_per_serving=None)` silently skips the field** instead of clearing to NULL. User clears a numeric cell in the data editor, sees it go blank, but the old value persists in the DB. Same bug exists in `update_recipe` for `cook_time_min`, `instructions`, `source`.
2. **`+ New Recipe` inserts an empty "New Recipe" row immediately**, before the user fills the form. Cancel or navigate-away leaves orphan stubs in the recipe list permanently.
3. **`apply_imports` has no pre-insert existence check.** Sequential `--apply` runs are naturally idempotent (because `compute_diff` re-evaluates DB state each call), but a TOCTOU race between `compute_diff` and `apply_imports` (concurrent runs, or photo-intake firing during import) produces duplicate `recipes.title` rows. Defense-in-depth fix.

---

## Pre-flight

1. `cd ~/Documents/GitHub/Home-Tools` (laptop) — this is a code-only change, mini deployment is just a `git pull` afterward.
2. Confirm working tree state: `git status -sb`. If anything in `console/tabs/plan.py`, `console/tabs/_recipe_form.py`, `jobs/enqueue_http.py`, `meal_planner/tests/test_read_result_or_synthesize_error.py` is modified-but-not-committed, those are the auto-fixes from the prior review pass — commit them first as `chore: Phase 18 review auto-fixes (mechanical)` on `main`, push, then start the plan branch from there. If clean, just branch.
3. `git checkout -b fix/phase18-review-fixups main`.
4. Read these for context:
   - `meal_planner/queries.py` — current `update_recipe` and `update_ingredient` shapes
   - `console/tabs/plan.py` — the `_render_edit_panel` flow + the `+ New Recipe` button at ~line 156
   - `meal_planner/scripts/export_sheet_to_db.py` — `apply_imports` per-recipe loop
   - The most recent journal entry — A3 review notes + auto-fix list

---

## Implementation

### Step 1 — Sentinel pattern in `queries.py` (Finding 1, foundation)

**File:** `meal_planner/queries.py`

Add at module top (after imports, before `_now_utc`):

```python
class _Unset:
    """Sentinel for partial-update kwargs.

    `None` means "set this field to NULL". `_UNSET` means "do not change
    this field". Distinguishes "explicitly clear" from "not provided".
    """
    __slots__ = ()
    def __repr__(self) -> str:
        return "<UNSET>"

_UNSET: _Unset = _Unset()
```

For `update_recipe`:
- Change every nullable kwarg default from `None` to `_UNSET`.
- Type annotation: `str | None | _Unset = _UNSET` (etc.).
- Replace every `if X is not None:` guard with `if X is not _UNSET:`.
- The `fields[X] = X` assignment still passes `None` through to the SQL UPDATE — `None` becomes SQLite NULL via the parameterized query.

Same transformation for `update_ingredient`. The `name` field is special — it's `NOT NULL` in the schema, so passing `name=None` would IntegrityError. That's the right behavior; don't add a guard against it.

`add_ingredient` and `create_recipe` keep their existing `None`-default kwargs (they're inserts, not partial updates — `None` means "use SQL default / store NULL," which is already the desired behavior).

`set_recipe_tags`, `delete_recipe`, `delete_ingredient` — no change.

### Step 2 — Sentinel-aware call sites in `plan.py` (Finding 1, completion)

**File:** `console/tabs/plan.py`

In `_save_recipe` (around line 399), the `update_recipe` call should explicitly clear textareas when empty:

```python
queries.update_recipe(
    recipe_id,
    title=payload["title"].strip(),
    base_servings=int(payload["base_servings"]),
    instructions=payload["instructions"] or None,  # "" → NULL
    cook_time_min=payload["cook_time_min"],         # int or None already
    source=payload["source"] or None,               # "" → NULL
    conn=conn,
)
```

In the ingredient `updates` loop (around line 415), `qty_per_serving=nan_to_none(...)` already produces `None` for cleared cells — that's now exactly what we want (it clears to NULL instead of being ignored). No call-site change needed for ingredients; the sentinel change in `queries.py` makes the existing call do the right thing.

### Step 3 — Pending-id tracking for "+ New Recipe" (Finding 2)

**File:** `console/tabs/plan.py`

Add a session-state-backed pending set. Insert near the top of `render` (or wherever the recipe tab entry point is):

```python
_PENDING_KEY = "_new_recipe_pending_ids"

def _pending_ids() -> set[int]:
    if _PENDING_KEY not in st.session_state:
        st.session_state[_PENDING_KEY] = set()
    return st.session_state[_PENDING_KEY]
```

In the `+ New Recipe` button handler (around line 155):

```python
new_id = queries.create_recipe(title="New Recipe")
_pending_ids().add(new_id)
st.session_state["_new_recipe_id"] = new_id
st.rerun()
```

In `_render_edit_panel`, add a Cancel button that handles the pending-set:

```python
if st.button("Cancel", key=f"edit_cancel_{recipe_id}"):
    if recipe_id in _pending_ids():
        queries.delete_recipe(recipe_id)
        _pending_ids().discard(recipe_id)
    _close_edit_panel(recipe_id)
    st.rerun()
```

In `_save_recipe` (after `st.success("Recipe saved.")`), drop the id from pending so future cancels don't delete:

```python
_pending_ids().discard(recipe_id)
```

If a "Cancel" button already exists in `_render_edit_panel`, replace its handler — don't add a second one. Verify by grep before adding.

### Step 4 — Pre-insert duplicate guard in `apply_imports` (Finding 3)

**File:** `meal_planner/scripts/export_sheet_to_db.py`

In `apply_imports`, inside the per-recipe `try` block (around line 232, before `insert_recipe` is called), add:

```python
existing = conn.execute(
    "SELECT id FROM recipes WHERE LOWER(title) = LOWER(?)",
    (title,),
).fetchone()
if existing:
    logger.info(f"{prefix} — title already in DB (id={existing['id']}), skipping")
    failed += 1
    conn.close()
    continue
```

The `conn.close()` matters because the conn was opened just before the try — if we `continue` without closing, we leak it. The existing `try/except/finally` block handles this on the normal paths.

Actually re-check the surrounding flow — if the conn is opened in a `try` with a `finally: conn.close()`, the `continue` inside the try will trigger the finally and close it for free. Read the file first; only add explicit `conn.close()` if the existing structure needs it.

### Step 5 — Tests

**New tests in `meal_planner/tests/test_queries.py`:**

```python
def test_update_recipe_clears_cook_time_to_null():
    # create with cook_time_min=30, then update with cook_time_min=None
    # assert get_recipe(id).cook_time_min is None

def test_update_recipe_clears_instructions_to_null():
    # similar — None means clear

def test_update_recipe_omitted_kwarg_does_not_clear():
    # update with no cook_time_min kwarg → field unchanged
    # this verifies _UNSET sentinel still skips correctly

def test_update_ingredient_clears_qty_to_null():
    # add ingredient with qty=2.5, update with qty_per_serving=None
    # assert list_ingredients()[0].qty_per_serving is None

def test_update_ingredient_omitted_kwarg_does_not_clear():
    # similar omitted-kwarg verification for ingredients
```

**New file `console/tests/test_plan_pending_ids.py`** (~40 LOC):

Pure-function tests for the pending-id tracking. Don't try to test Streamlit UI — extract the set-management logic into a small testable helper module if needed (e.g., `console/tabs/_pending_recipes.py` with `add`, `discard`, `contains`).

```python
def test_pending_set_adds_and_removes():
    # given a session_state-like dict, exercise the helpers

def test_save_clears_from_pending():
    # adding then save → not in set

def test_cancel_with_pending_deletes():
    # cancel handler integration: assert delete_recipe called when in set,
    # not called when not in set (mock queries.delete_recipe)
```

If extracting a helper module pushes scope, write the tests against the helpers as inline private functions in `plan.py`. Don't gold-plate.

**New tests in `meal_planner/tests/test_export_sheet_to_db.py`:**

```python
def test_apply_imports_skips_existing_title(tmp_path):
    # use real in-memory SQLite + tmp DB_PATH; insert "Beef Stew" via
    # create_recipe; mock _parse_ingredients to return a fixed dict;
    # call apply_imports with a single ("Mains", "Beef Stew", [...]) tuple;
    # assert imported=0, failed=1; assert list_recipes() length unchanged.

def test_apply_imports_inserts_new_title(tmp_path):
    # happy path: title not in DB → insert succeeds, imported=1.
```

`_parse_ingredients` calls live Gemini — it MUST be mocked. Use `monkeypatch.setattr` on the module-level reference, not the original.

---

## Test gate

```bash
python3 -m pytest meal_planner/tests/ console/tests/ jobs/tests/ -q --tb=short
```

Must show: `<all-tests> passed, 0 failed`. The Phase 18 baseline is 379 passed; this plan adds ~10 new tests, so expect ~389 passed.

If any pre-existing test fails (i.e., not one of the new ones), the sentinel change broke a backward-compat assumption. Read the failure, decide whether the test was wrong (was it asserting the buggy "skip on None" behavior?) or whether the change broke something. Fix forward, don't paper over.

---

## Commit + push

Single commit on the branch. Message:

```
fix: Phase 18 post-review fixups — sentinel updates, orphan recipe, idempotency

- queries.py: _UNSET sentinel for update_recipe + update_ingredient so
  callers can explicitly clear nullable fields to NULL (was silently
  skipped when None was passed). Adversarial review F1.
- plan.py: track new-recipe pending ids in session_state; Cancel deletes
  the orphan stub if Save never fired. Adversarial review F2.
- export_sheet_to_db.py: pre-insert existence check in apply_imports for
  TOCTOU defense (concurrent --apply runs or photo-intake collision).
  Adversarial review I1.
- Tests: ~10 new (sentinel clear-to-null, omitted-kwarg-skip, pending-set
  transitions, apply_imports duplicate-skip).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Then `git push -u origin fix/phase18-review-fixups`.

Open a PR with `gh pr create --base main --fill`. The PR body should reference this plan file path so the reviewer can audit completeness.

---

## Opus review (final step — DO NOT skip)

After the commit + push + PR-creation, **do not stop**. Spawn an Opus review agent via the Agent tool with this prompt:

> You are doing a pre-merge Opus code review of the fix branch `fix/phase18-review-fixups` against `main`. The branch implements three fixups from a prior Opus full-review of Phase 18; the implementation plan is at `Mac-mini/PHASE18_REVIEW_FIXUPS.md` — read it first.
>
> Run `git diff main..HEAD` and verify:
>
> 1. **Sentinel correctness.** `update_recipe` and `update_ingredient` use `_UNSET` defaults, switch every `is not None` guard to `is not _UNSET`, and DON'T accidentally pass `_UNSET` into the SQL parameter binding (that would crash sqlite3). Trace one full path manually: caller passes `qty_per_serving=None` → reaches the `fields["qty_per_serving"] = None` assignment → ends up in the parameterized UPDATE → SQLite stores NULL.
> 2. **Pending-id correctness.** Cancel handler deletes only when the id is in the pending set (else it would delete saved recipes). First successful Save discards from the set so subsequent saves of the same recipe don't trigger delete-on-cancel afterwards.
> 3. **apply_imports duplicate-skip.** The existence check uses the same `conn` as the subsequent insert (no separate connection — would defeat TOCTOU defense). The `failed` counter increments and the loop continues. The conn is properly closed on the skip path (verify against the surrounding try/finally — if it isn't, fix it).
> 4. **Test coverage.** All ~10 new tests exist and the full suite passes (`python3 -m pytest meal_planner/tests/ console/tests/ jobs/tests/ -q`). Specifically verify the new "omitted kwarg does not clear" tests, because that's the regression class the sentinel pattern is supposed to prevent.
>
> **Action policy:**
> - If you find a mechanical issue (typo, missing import, dead code, wrong line of a docstring, failing test that's clearly wrong about new behavior), FIX IT YOURSELF in a fixup commit on the same branch. Use commit message `fix: Opus review — <one-line summary>`. Do not push the fixup; leave it for the user to push.
> - If you find an architectural issue (the sentinel design is wrong, the pending-set has a race, the existence check needs a different approach, the API needs to change), STOP and write a short markdown summary of the concern + 2-3 options to `Mac-mini/PHASE18_REVIEW_FIXUPS_OPUS_NOTES.md`. Do not commit anything. Print the summary path to the console for the user.
> - If everything is clean, print "Opus review clean — ready to merge." and stop.
>
> Do not push. Do not merge. Do not modify anything outside this branch's scope. Use `model: opus` (you should already be running on Opus — verify by checking your model identity).

Pass `model: "opus"` to the Agent tool call. The agent runs end-to-end, makes its findings, and stops.

After the agent returns, surface its summary to the user verbatim — don't editorialize. The user decides whether to push the fixup commit (if any), open the notes file (if escalated), or merge.

---

## Done criteria

- Branch `fix/phase18-review-fixups` exists, contains 1 implementation commit + (optionally) 1 Opus fixup commit
- All tests pass
- PR is open against `main`
- Either "Opus review clean — ready to merge." has been printed, OR `Mac-mini/PHASE18_REVIEW_FIXUPS_OPUS_NOTES.md` exists with escalated questions
- Sonnet's final user-facing message: a one-paragraph summary of what was done + the Opus agent's verdict + the PR URL

That's the stop point. The user pushes the fixup commit (if any), reads the notes (if any), and merges when ready.
