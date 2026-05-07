# Mac mini Home Server — Working Plan

Living plan for the ongoing build. Update as phases advance. Pair this with
`Mac-mini/README.md` (state-of-the-project), `Mac-mini/PHASE6.md` (Phase 6
operator runbook), `Mac-mini/history/` (completed-phase porting recipes), and
the `~/.claude/projects/.../memory/` entries (the accumulated lessons).

---

## Naming convention

A **Phase** is confirmed scope, completable in one sitting, sequentially
numbered (no decimals — rule applies starting at Phase 13; Phase 12.5 is
grandfathered). A **Pick** is a catalogued suggestion (see brainstorm at
`~/.claude/plans/come-up-with-more-encapsulated-spring.md`); Picks remain
suggestions until explicitly promoted to a Phase, at which point the Pick
number is retired and only the new Phase number is used.

---

## Quick status (as of 2026-05-04)

**Phase 7 NAS backup LIVE on the mini** (commit `5f806aa`, 2026-05-01):
two restic repos at `~/Share1/mac-mini-backups/{restic-hourly,restic-daily}`
on the iananny NAS. Hourly agent backs up `health.db` at every :17;
daily agent at 03:30 backs up state.json + event_log.jsonl + .env +
finance.db + nas-intake/state.json + login.keychain-db + incidents.jsonl;
weekly prune Sunday 04:00. All 13 deploy gates passed including bare-metal
recovery dry-run. Recovery secrets in 1Password "Mac mini home server
recovery" Secure Note. Operator runbook at `Mac-mini/PHASE7.md`; bootstrap
recovery doc at `Mac-mini/RECOVERY.md`. Time Machine + off-site (B2) deferred.

Phase 6 monitoring layer LIVE on the mini (commit `a13c41a`, 2026-04-30):
heartbeat (every 30 min) → `incidents.jsonl` → daily Slack digest at 07:00
to `#ian-event-aggregator` + weekly SSH-failure digest. Three new LaunchAgents
(`com.home-tools.heartbeat`, `daily-digest`, `weekly-ssh-digest`). Operator
runbook at `Mac-mini/PHASE6.md`. (Heartbeat extended in Phase 7 with a
backup_health probe that ignores in-flight runs.)

Everything Phase 5 and earlier is done; recipes preserved in
`Mac-mini/history/` (5b health-dashboard, 5c service-monitor, 5d NAS mount,
5e nas-intake v1).

The live agent registry is `service-monitor/services.py:SERVICES`. The
service-monitor Streamlit dashboard at `http://homeserver:8502/` shows live
status (PID, last exit, schedule, queue depths, DB sizes, Ollama state, log
tails) for every loaded `com.home-tools.*` and `com.health-dashboard.*` agent.

---

## Resume from here

**Phase 12.5 DONE 2026-05-04 ✅** (commits `028dd0d` → `95e3d0a` →
`0cf1b7b` → `df12304` → `4873d8f` → `7927bf0` → `79fdfef` → `a242e30`
→ `748cb09`). Event-aggregator fetch + worker migrated to huey kinds;
legacy worker loop retired. Both migrations promoted. Full record in
`Mac-mini/PHASE12.md` "Phase 12.5 follow-up" section.

**Phase 13 architecting DONE 2026-05-01 ✅** — approved design at
`~/.gstack/projects/ianereed-Home-Tools/ianereed-main-design-20260501-132248.md`.
Approach C2 (fills Phase 12's reserved Plan slot). Locked decisions in
`project_meal_planner_expansion_priority.md` memory.

**Phase 14 DONE 2026-05-04 ✅** — Meal-planner V0 shipped. Recipes tab live
at `http://homeserver:8503/?tab=recipes`. SC6 verified by Ian dogfood
(11 consolidated tasks landed in Todoist correctly); Anny walkthrough still
pending.

**Phase 14.8 DONE 2026-05-05 ✅** — Clear-all Todoist button shipped (commit
`952f4a2`). Dogfood: 12 tasks created → clear job fired → 0 meal-planner
tasks remain, 40 event-aggregator tasks untouched.

**Phase 14.9 DONE 2026-05-04 ✅** — Multi-recipe grid shipped (commit
`94c2259`). Dogfood: 2 recipes selected → 18 consolidated grocery tasks
created → 0 after clear. Event-aggregator 40 tasks untouched. All 142 tests
pass.

**Phase 14.10 DONE 2026-05-05 ✅** — Bypass consolidation; raw scaled lines
per recipe (commit `090bb69`). Kind no longer calls Gemini. Each ingredient
emits as a separate Todoist task with `(Recipe Name)` suffix. 143/143 tests
pass. **Live-verified 2026-05-05 11:30** — task `4d66f94b` produced 14
Todoist tasks with `(Broccoli & Lemon Risotto)` suffix on every line.
First dogfood (task `4d267f5b`) ran on a stale consumer process from
before the merge — required `launchctl bootout`/`bootstrap` on
`com.home-tools.jobs-consumer` to reload the kind module. Lesson:
git pull is not deploy; the huey worker must be kickstarted/restarted
after merging changes to any `jobs/kinds/*.py` file.

**Phase 14.11 DONE 2026-05-05 ✅** — Tag filter on Recipes tab (commit
`1c165e8`). `st.pills` multi-select + AND/OR radio above the grid. `list_all_tags()`
helper added; `search_recipes()` extended with `tag_logic` param. 148/148 tests
pass.

**Phase 15 DONE 2026-05-06** — bake-off ran on llama3.2-vision:11b; production
prompt baseline + warm-reuse harness. Output: `meal_planner/eval/PHASE15_NOTES.md`.

**Phase 16 DONE 2026-05-07** — Recipe-photo intake live. NAS folder watched by
`meal_planner_photo_intake_scan` enqueues `meal_planner_ingest_photo`, which runs
llama3.2-vision via Ollama on the mini, validates schema, retries once on
malformed output, runs `_normalize.py` to fix qty/unit fusion bugs, inserts the
recipe + ingredients + tags into `recipes.db`, and renames the photo into `_done/`
with a sidecar JSON. Chunk F (`cce769c`) added the deterministic post-extraction
normalizer; review-fixes pass (`4b38f10`) hardened multi-token units, Pattern 2
over-fire guards, retry-path normalization, and DB-persisted normalize warnings.
273/273 tests pass.

**Phase 17 — UI polish (in progress).**

**Chunk A DONE 2026-05-07** (`b560a6d`) — Categorized tag pills: split the flat
`st.pills` row into three labeled groups (Cuisine / Meat+diet / Other) driven by
`meal_planner/tag_categories.py:CATEGORY_MAP`. 6 new tests; 279/279 pass.

**Chunk B DONE 2026-05-07** (`e590aa6`) — Alpha-sort toggle: `st.toggle("Alphabetical", value=True)`
above the grid. Default on = alpha by title; off = id DESC (most-recently-added). `sort` param
added to `search_recipes()`; validated before SQL composition. 5 new tests; 566 pass.

**Next: Chunk C** — Todoist-success indicator via huey result polling.

**Then: Phase 18 — Edit recipes via web GUI + Sheet decommission +
jobs-queue bug fix.** Two workstreams bundled in one phase:

1. **Web-edit recipes + decommission the Apps Script Sheet fallback** —
   move recipe edits into `console/tabs/plan.py`; the Sheet stops being
   the source-of-truth (it's been a read-only fallback since Phase 14).
2. **Jobs-queue bug fix** — two bugs surfaced 2026-05-07 (see
   `memory/project_nas_intake_worker_wedge_bug.md` and `journal-135.md`
   + `journal-136.md`): nas_intake_scan starved the shared huey worker
   for ~25 min, and the long-running streamlit held an orphan WAL fd
   that silently dropped two send-to-Todoist enqueues.

Both workstreams land on `fix/phase18-recipe-edit-and-jobs-queue` (or
two sibling branches that merge together), separate from Phase 17 so
the Phase 17 UI work isn't destabilized. Detail for each in the Phase
18 section below.

Pre-flight (confirm health before starting new work):

```bash
ssh homeserver@homeserver '
  tailscale status | head -3
  launchctl list | grep -E "com\.(home-tools|health-dashboard)" | head
  curl -sf http://127.0.0.1:11434/api/tags | head -c 80; echo
  ls ~/Home-Tools/run/digest-failed.flag 2>&1 | head -1
  tail -3 ~/Home-Tools/logs/incidents.jsonl
'
```

Expected: tailscale connected, agents registered, Ollama responds,
`digest-failed.flag` missing, incidents.jsonl quiet.

---

## Phase 6 — Minimal monitoring (DONE 2026-04-30)

Daily Slack digest replaces the original Pushover design (user declined to pay
for Pushover; trade-off accepted: failures surface at 07:00 next morning
instead of immediately).

Three new agents — heartbeat (30-min liveness check), daily-digest (07:00),
weekly-ssh-digest (Mon 09:00). Helper scripts in `Mac-mini/scripts/`. Phase 6
touches no existing services; rollback is clean (unload + rm three plists).

Full operator runbook, file inventory, format examples, test gates,
troubleshooting, and rollback at **`Mac-mini/PHASE6.md`**.

---

## Phase 7 — Backup (DONE 2026-05-01 — NAS-only)

Goal: 3-2-1 backup so we can recover from disk failure or ransomware. Now
that `health.db` is the authoritative copy (laptop's DB is frozen at the
2026-04-22 cutover), losing it means re-scraping from Intervals + Strava
APIs, which only cover recent data. Protect it.

### What actually matters to protect (priority order)

1. `~/Home-Tools/health-dashboard/data/health.db` (~91MB, authoritative)
2. `~/Home-Tools/event-aggregator/state.json` + `event_log.jsonl`
3. `~/Home-Tools/finance-monitor/data/finance.db`
4. `~/Home-Tools/nas-intake/state.json`
5. `~/Library/Keychains/login.keychain-db` (7+ secrets, painful to re-migrate)
6. `~/Home-Tools/logs/incidents.jsonl` (Phase 6 audit trail)

### Decision: NAS-only for v1 (locked 2026-05-01)

Backup target is the iananny NAS (192.168.4.39) Share1 already mounted at
`~/Share1`. Not an external SSD. Not B2/Wasabi. Rationale:

- It already exists, already credentialed, already mounted.
- 3-2-1 isn't fully met with NAS-only (still on the same LAN as the mini),
  but it's a strong first leg — protects against mini SSD failure, OS
  reinstall, accidental `rm -rf`. **Open to off-site (B2/restic) as a second
  leg in the future**, not in scope for this Phase.
- Phase 5d already proved NAS reachability + TCC + autofs-style remount
  patterns work; Phase 7 doesn't have to re-solve that.

### What shipped

- **Two restic repos** at `~/Share1/mac-mini-backups/restic-hourly/` and
  `~/Share1/mac-mini-backups/restic-daily/` (encrypted, content-defined
  chunked, deduplicated). Independent retention per repo.
- **Three LaunchAgents**:
  - `com.home-tools.restic-hourly` — every :17, backs up `health.db`
  - `com.home-tools.restic-daily` — 03:30 daily, backs up state.json +
    event_log.jsonl + .env + finance.db + nas-intake/state.json +
    login.keychain-db + incidents.jsonl + meal_planner/recipes.db +
    meal_planner/seed_progress.json
  - `com.home-tools.restic-prune` — Sun 04:00 weekly, runs
    `restic prune` against both repos
- **Recovery secrets** in 1Password Secure Note "Mac mini home server
  recovery" — 5 fields: 2 restic passwords + NAS_USER/PASSWORD/IP. The
  in-repo `Mac-mini/RECOVERY.md` is the bootstrap walkthrough; it points
  at 1Password but never contains the live passwords.
- **Heartbeat extended** with a `backup_health` probe that emits stale
  incidents into the Phase 6 daily-digest pipeline. Ignores logs <60 s
  old to avoid in-flight false-positives.
- **service-monitor** registry now shows the 3 backup agents in a "Backup"
  swim-lane on the dashboard.

### Decisions made (locked)

- **Time Machine dropped from v1.** TM-on-NAS encryption from CLI is
  fragile and unencrypted-on-NAS is a privacy regression. Phase 7.5 if
  ever wanted = USB SSD with TM-via-GUI.
- **Off-site (B2/Wasabi) deferred.** Phase 7.5 if/when something makes
  it feel necessary.

### Files

Implementation plan (with all 8 open questions resolved + outside-voice
findings folded in) at `~/.claude/plans/phase-7-nas-backup.md`. Operator
runbook at `Mac-mini/PHASE7.md`. Recovery doc at `Mac-mini/RECOVERY.md`.

---

## Phase 8 — Finance automation (Phases 1 + 2 LIVE)

Work at `~/Home-Tools/finance-monitor/`. Two LaunchAgents on the mini:
KeepAlive Slack DM bot (`com.home-tools.finance-monitor`) + 5-min interval
watcher (`com.home-tools.finance-monitor-watcher`, runs read-only YNAB API
sync at the top of each cycle, then file intake).

- Phase 1 (DONE 2026-04-23): Slack DM Q&A over a local SQLite mirror; PDF
  + image OCR ingestion; query engine via qwen3:14b. DM allowlist locked,
  60s/user rate limit, sender ID audit-logged.
- Phase 2 (DONE 2026-04-24): read-only YNAB API delta sync via `YnabClient.get()`
  (the *only* HTTP method on the client — never add write methods).
  `budget_months` + `sync_state` tables. Cutoff `YNAB_API_CUTOFF=2026-04-24`.

**Phase 3+** (deferred): Amazon order reconciliation via Gmail; daily/weekly
spending digests; anomaly detection.

**Security:** YNAB PAT in `.env` (PAT has full read+write at YNAB's level;
read-only is enforced **client-side**). No LangChain (active critical CVEs).
All data local. Slack bot DM-only.

Comprehensive runbook at `finance-monitor/TROUBLESHOOTING.md`.

---

## Phase 9 — Slack UX split (dispatcher LIVE)

`Home-Tools/dispatcher/` is live on the mini. Long-running Socket Mode bot
listens in `#ian-event-aggregator` (interactive commands) and
`#ian-image-intake` (file uploads). Routes images locally via qwen2.5vl,
drops financial docs into `finance-monitor/intake/`, invokes
`event-aggregator main.py ingest-image` for event-type files. All intake
local-only — cloud fallback was removed; PDF rasterization via `pypdfium2`.

Tier-2 commands (mute/watch, force scan, undo last, changes since) shipped
2026-04-24; ACKs ephemeral 2026-04-27. Health check at
`Mac-mini/scripts/dispatcher-3day-check.sh` (see memory
`reference_dispatcher_health_check.md`).

---

## Phase 12 — Mini Jobs framework + Mini Ops console (DONE 2026-05-01 ✅)

Replaced 12 cron-style LaunchAgents with `@huey.periodic_task` Job kinds
in `jobs/kinds/`. Operator runbook: **`Mac-mini/PHASE12.md`**.

- `jobs/` — huey foundation, adapters (slack/gcal/todoist/card/nas/sheet),
  `migration_verifier` (hourly auto-rollback on baseline divergence),
  CLI (`enqueue/status/kinds/new/doctor/migrate/rollback/cleanup-soaked`),
  HTTP enqueue at `homeserver:8504` (Tailscale-bound, bearer-token auth).
- `console/` — Streamlit "Mini Ops" at `homeserver:8503`. Tabs:
  Jobs, Decisions, Ask, Intake, Plan (placeholder for Phase 13).
  Sidebar: Settings status panel.
- 12 migrations land in one commit; cutover per-kind via
  `bash jobs/install.sh migrate-all`. Each migration's `@baseline` metric
  is checked hourly; 72 consecutive successes → auto-promote (delete
  `.plist.disabled`); divergence → auto-rollback (rename back, kickstart
  old plist). Net plist count: 21 → 10 in service-monitor's `SERVICES`.
- Closes OPS6: `event-aggregator/state.py:save()` now requires an active
  `state.locked()` block (RuntimeError otherwise); 32+ callsites wrapped.

Plan source (v3): `~/.claude/plans/phase-12-mini-jobs-queue.md`
Deferred to Phase 12.5: `event-aggregator.fetch` + worker (the queue +
model-swap state machine doesn't decouple cleanly from fetch).

**Health migrations deferred (2026-05-04):** `health_collect`,
`health_intervals_poll`, `health_staleness` huey kinds exist and fire on
schedule, but `jobs.cli migrate` was never run on them — no
`migrations.json` entry, no verifier baseline, original plists unloaded
but not renamed to `.disabled`. Operationally fine. Punted to a later
phase; close out with `jobs.cli migrate <kind>` then `promote` for each.

## Phase 12.5 — Event-aggregator on the Jobs framework (DONE 2026-05-04 ✅)

All sub-phases complete. Full record in `Mac-mini/PHASE12.md` "Phase 12.5
follow-up" section.

- ✅ **12.5** — fetch → `@huey.periodic_task` (commit `028dd0d`)
- ✅ **12.6** — `@requires_model` primitive in `jobs/lib.py` (commit `95e3d0a`)
- ✅ **12.7** — worker decomposed into 3 huey kinds (commits `0cf1b7b`, `df12304`)
- ✅ **12.8a** — 22 pre-promote fixes (commits `4873d8f`, `7927bf0`)
- ✅ **12.8b** — promote + worker loop retired (commits `79fdfef`, `a242e30`, `748cb09`)

**Deferred** (logged in PHASE12.md): F (importlib exec_module leak), G
(decision_poller cross-lock), H (3 pre-existing `test_proposals.py` failures).

## Phase 13 — Meal-planner overhaul: architecting (DONE 2026-05-01 ✅)

Design approved via /office-hours + gstack review pipeline. Approach C2
(meal-planner fills Phase 12's reserved Plan slot). Locked decisions in
memory: `project_meal_planner_expansion_priority.md`. Approved design doc:
`~/.gstack/projects/ianereed-Home-Tools/ianereed-main-design-20260501-132248.md`.

## Phase 14 — Meal-planner V0 (DONE 2026-05-04 ✅)

Recipe DB + Recipes tab in console + send-to-Todoist Job kind + sheet seed +
`console/app.py` deep-link refactor. Phases 14.1–14.7 all landed on
`phase14/meal-planner-v0`. Key commits: package cutover (14.1), read API +
Recipes tab (14.2), Sheet seeder (14.3), Todoist adapter (14.4),
consolidation + send-to-Todoist kind (14.5), deep-link refactor + rename
(14.6), V0 ship + infra fixes (14.7).

Infra fixes shipped in 14.7: `jobs/run-consumer.sh` now sources
`meal_planner/.env`; `requests` added to `jobs/requirements.txt`.

Success Criteria status: SC1 ✅ deep-link works, SC2 16 recipes (dataset
ceiling), SC3 tags TBD post-Anny-walkthrough, SC4 ✅ dropdown+slider+button
render, SC5 ✅ kind registered in huey, SC6 deferred to Anny walkthrough.

## Phase 14.8 — Recipes tab: "Clear all meal-planner items from Todoist" button (DONE 2026-05-05 ✅)

V0 polish. "Clear all meal-planner items from Todoist" button below Send-to-Todoist.

Shipped in commit `952f4a2`:
- `jobs/kinds/meal_planner_clear_todoist.py` — lists via `GET /api/v1/tasks?label=meal-planner`
  (paginated via next_cursor), deletes per-task, collects failures, returns
  `{"deleted": N, "failed": M, "failed_ids": [...]}`. `LABEL = "meal-planner"` is
  a module-level constant (safety boundary).
- `jobs/tests/test_meal_planner_clear_todoist.py` — 7 tests; all pass.
- `console/tabs/plan.py` — two-click confirm button (st.session_state timestamp pattern).
- `meal_planner/README.md` — note that label is a code constant, not an env var.

Dogfood 2026-05-05: 12 meal-planner tasks created, clear job fired, 0 tasks remaining,
40 event-aggregator tasks untouched. Exit gate: all 10 items passed.

## Phase 14.9 — Recipes tab: multi-recipe grid (DONE 2026-05-04 ✅)

Replaced single-recipe selectbox + slider + ingredient table with a `st.data_editor`
multi-recipe grid. Three columns: Send (CheckboxColumn), Recipe (TextColumn,
disabled), Servings (NumberColumn, min=1, max=20, step=1, default=base_servings).

Shipped in commit `94c2259`:
- `console/tabs/plan.py` — `_render_inner()` replaced with grid + Send button.
  `_render_clear_button()` unchanged.

Dogfood 2026-05-04: 2 recipes selected (Anny's Ji dan ×4 + Broccoli & Lemon Risotto ×6),
18 consolidated grocery tasks created. Clear confirmed 0 remaining.
Event-aggregator count 40 — untouched. 142/142 tests pass.

Next UI iterations (not yet scoped):

- **Ingredient-edit view** — adjust per-recipe quantities from the console
  before sending.
- **End-to-end success indication on the Recipes tab.** Today the
  "Job enqueued — task ID: …" toast paints green regardless of what happens
  inside the kind. The 2026-05-04 quota incident produced a green toast even
  though 0 Todoist tasks were created. The UI should show the actual outcome
  of the run: full success (N items sent), partial (M of N), or failure
  (consolidation 429, Todoist auth, etc.). Likely needs the kind to write
  its result where the tab can poll (huey result store, or a
  `meal_planner_runs` table), then a status block on the Recipes tab.

## Phase 14.10 — Recipes tab: bypass consolidation (DONE 2026-05-05 ✅)

`meal_planner_send_to_todoist` no longer calls Gemini consolidation.
Shipped in commit `090bb69`:
- `jobs/kinds/meal_planner_send_to_todoist.py` — removed `consolidate_for_grocery`
  import and `GEMINI_API_KEY` env read. For each `(recipe, target_servings)` pair,
  calls `scale_ingredients()` and emits one Todoist task per ingredient.
  Title format: `"{qty:.4g} {unit} {name} ({Recipe.title})"` (unit omitted if None,
  qty omitted if None). Section routing uses `Ingredient.todoist_section` directly;
  unknown/None section falls back to first key in `TODOIST_SECTIONS`.
  `source_id` per task is `f"recipes:{recipe.id}"`.
- `jobs/tests/test_meal_planner_send_to_todoist.py` — rewritten with 5 tests,
  no Gemini mocks. 143/143 tests pass.
- `consolidation.py` left on disk untouched.

## Phase 14.11 — Recipes tab: tag filter (DONE 2026-05-05 ✅)

Tag filter above the multi-recipe grid on the Recipes tab. Resolves SC3.

- `meal_planner/queries.py` — added `list_all_tags(*, path)` helper (returns
  sorted distinct tags linked to ≥1 recipe, orphan tags excluded via JOIN).
- `meal_planner/queries.py` — extended `search_recipes()` with
  `tag_logic: str = "and"` param. OR mode uses EXISTS/IN subquery. Raises
  `ValueError` on unrecognized logic value.
- `console/tabs/plan.py` — renders `st.pills` (Streamlit 1.57 on mini, well above
  the 1.40 requirement) + `st.radio("Match", ["AND","OR"])` above the grid.
  Empty selection = all recipes. Filter-active empty-state message distinguished
  from DB-empty message.
- `meal_planner/tests/test_queries.py` — 5 new tests: orphan exclusion, OR union,
  AND intersection, empty tags = all, invalid logic raises. 148/148 tests pass.

## Phase 15 — Recipe-photo-LLM bake-off (DONE 2026-05-06)

Research only — no production code. Output: `meal_planner/eval/PHASE15_NOTES.md`.
Picked **llama3.2-vision:11b** via Ollama on the mini (local; no API quota
exposure). Bake-off harness in `meal_planner/eval/bake_off.py` with
warm-reuse + relaxed F1 + per-call `keep_alive_override`. Synonyms +
unicode-fraction expansion in `meal_planner/eval/synonyms.yml`.

Entry gate (Anny's full SC walkthrough SC1–SC6) passed during Phase 14.11.

**Open question — API quota visibility.** Google's Gemini API has no
programmatic quota-check endpoint; the only signals are 429s at request time,
the AI Studio dashboard (manual UI), or GCP Console (if linked). On 2026-05-04
a `meal_planner_send_to_todoist` run silently produced 0 Todoist tasks because
free-tier `gemini-2.5-flash-lite` RPD (20/day) was exceeded — AI Studio
showed 24/20. The retry loop in `consolidation.py:_call_gemini` ran 4 attempts,
each got 429, and RPD is a 24h rolling window so retries can't recover. The
kind then returned an empty grocery list, the UI showed a green "Job enqueued"
toast, and we only noticed because Todoist was empty. If Gemini wins the
bake-off, we need a local API counter (per-key, per-day, per-model) so we can
tell when the daily limit is closing in before users hit silent failures.
Whichever provider wins should get the same treatment.

## Phase 16 — Recipe-photo intake (DONE 2026-05-07)

Pipeline: NAS folder `Share1/Documents/Recipes/photo-intake/` →
`meal_planner_photo_intake_scan` (every 60s, computes sha, dedups against
`photos_intake` table, moves to `_processing/`) → `meal_planner_ingest_photo`
(preprocess image, call Ollama vision, normalize, insert recipe + tags +
ingredients, rename to `_done/<sha>.jpg` + `<sha>.json` sidecar).

**Chunks shipped:**

- **Chunk 1** — Schema add: `photos_intake` table with sha-keyed dedup;
  `meal_planner.db.init_db` extended.
- **Chunk 2** — `meal_planner_photo_intake_scan` + `meal_planner_ingest_photo`
  job kinds; `_processing/` / `_done/` directory state machine; status row per
  photo (pending → extracting → ok / ok_partial / ollama_error).
- **Chunk 2.5** — Stuck-extracting recovery, rename split-brain fixes, scan
  self-heal (`5793488`).
- **Chunk 2.6** — Never-drop ingestion: prompt tightening, sidecar JSON,
  tag persistence (`f55f8a8`).
- **Chunk F** — Post-extraction normalizer `_normalize.py` (`cce769c`):
  three deterministic patterns fix LLM qty/unit output bugs without touching
  the prompt. Replay validation: scale_ok 76.7% → 97.7%, F1 0.754 → 0.761.
- **Review-fix pass** (`4b38f10`): multi-token units (`fl oz`,
  `fluid ounces`), Pattern 2 over-fire guards (`slice of bread`, single-word
  unit names), retry-path always normalizes, Pattern 3 emits a "discarded
  unit content" warning, replay dedup gates on scoreable status, DB
  persists `normalize_warnings`. 273/273 tests pass.

Production `meal_planner_ingest_photo` runs on the mini's
`com.home-tools.jobs-consumer` LaunchAgent. Live test: Nanaimo Bars PDF
processed end-to-end 2026-05-06.

## Phase 18 — Edit recipes via web GUI + Sheet decommission + jobs-queue bug fix (SCOPED 2026-05-07, not yet started)

Two workstreams in one phase. Lands on
`fix/phase18-recipe-edit-and-jobs-queue` (or sibling branches that
merge together), separate from Phase 17 so UI polish isn't
destabilized.

### Workstream A — Edit recipes via web GUI + Sheet decommission

Move recipe-row editing into the Recipes tab so `recipes.db` becomes
the sole source-of-truth. Today the Apps Script Sheet is a read-only
fallback (Phase 14); after Phase 18 it's retired. Detailed scope to be
filled in at the Phase 18 office-hours session — likely an inline
edit-row affordance per recipe in `console/tabs/plan.py`, persistence
via `meal_planner.queries.update_recipe(...)`, and a one-shot script
that exports the current Sheet state into `recipes.db` then archives
the Sheet to read-only.

### Workstream B — Jobs-queue bug fix

Two bugs surfaced same session — both real, both confirmed live on the
mini:

1. **nas_intake_scan starves the shared huey worker.** A multi-page
   healthcare PDF held Worker-1 for ~25 min while 13+ periodic tasks
   queued behind it. v1.1 large-file escalation never armed because the
   small-file path completed in one shot — the `timeout_counts >= 3`
   rule only increments on `subprocess.TimeoutExpired`, so a 590s
   successful run never triggers escalation. Single-worker consumer
   (`-w 1`) means any slow non-model kind starves every other kind.
2. **Streamlit holds orphan SQLite WAL fd, silently drops enqueues.**
   Long-running mini console (`com.home-tools.console`, started May 5)
   held WAL/shm fds on inodes that no longer existed in any directory
   entry. INSERT INTO task returned cleanly, huey returned a Result.id,
   "Job enqueued" banner showed — but the row landed in a deleted WAL
   the consumer could never read. Two clicks (`c5ab896e`, `346474b6`)
   both fell into the hole; Todoist confirmed never received the items.
   Immediate fix was a `launchctl kickstart -kp` of the streamlit; real
   fix is to remove the in-process huey import.

### Bug 1 — primary fix (1A)

`nas-intake/config.py`: `SUBPROCESS_TIMEOUT_S = 600 → 90`. After 3×90s
timeouts (~5 min) v1.1 escalation arms automatically and the file moves
to `ingest-image-large` (page-resumable, heartbeat-watchdog).

- **LOC:** 1.
- **Risk:** false-positive timeouts on slow-but-not-wedged PDFs — but
  those simply re-queue at the next 5-min tick and eventually escalate,
  which is the right outcome anyway.
- **Test:** replay the wedged healthcare PDF; expect 3× ~90s timeouts
  then escalation; large-file path completes the OCR.

### Bug 1 — deferred class fix (1B, separate follow-up branch)

Split queues — second `SqliteHuey(name="home-tools-jobs-bg")` for non-
model kinds, second consumer plist. Don't block Phase 18 on this; if 1A
holds, defer indefinitely. See full tradeoff write-up in journal-136.md.

### Bug 2 — primary fix (2A)

Route console enqueues through `jobs.enqueue_http` on port 8504 (the
service is already running but currently dormant — auth blocked because
`HOME_TOOLS_HTTP_TOKEN` keychain entry is missing).

Pre-req: `jobs/install.sh` adds an idempotent `add-generic-password`
step that creates `home-tools/jobs_http_token` (random 32-byte hex if
missing). Then `launchctl kickstart -kp gui/501/com.home-tools.jobs-http`
to pick up the env.

Code change:

- New `console/jobs_client.py` — POST to
  `http://100.66.241.126:8504/jobs` with bearer auth. ~50 LOC.
- `console/tabs/plan.py:96` and `:141` — replace
  `from jobs.kinds.X import X; X(...)` with
  `jobs_client.enqueue("X", {...})`. ~10 LOC delta.
- Add `GET /queue-size` endpoint to `jobs/enqueue_http.py` (~15 LOC),
  swap `console/tabs/jobs.py:42` and `console/sidebar/settings.py:17`
  to use HTTP. Removes the entire long-lived fd surface from the
  streamlit.

**Risk:** HTTP server outage → enqueues fail visibly with toast (which
is *better* than today's silent drop).

**Test:**

- `python -m jobs.cli doctor` sanity check.
- Console "Send checked recipes to Todoist" → Todoist actually
  populates within 30s.
- `lsof -p $(pgrep streamlit) | grep jobs.db` returns empty after
  shipping.
- Restart `com.home-tools.jobs-http`; verify console enqueues fail
  visibly (failure-path test).
- Long-soak: leave streamlit up overnight, re-run lsof — still empty.

### Bug 2 — fallback (2B)

If 2A blocks on infra, add a `jobs/__init__.py` helper that builds a
fresh `SqliteHuey` on demand and closes it after each call; replace the
three console-side imports with this helper. ~25 LOC, in-process pattern
preserved but fd is short-lived. Don't ship both 2A and 2B — they
conflict in maintenance burden.

### Cross-cutting

- Add memory `feedback_streamlit_in_process_huey` — "don't import a
  SQLite-WAL backend in a long-lived Streamlit process; route writes
  via HTTP."
- Update `Mac-mini/PHASE12.md` to document the keychain entry
  expectation for `jobs_http_token` and the rule "console writes go
  through 8504, not in-process huey".
- Flag follow-up: `health-dashboard/data/health.db` has the same long-
  lived-streamlit + WAL pattern (4 LaunchAgent collectors writing).
  Same vulnerability class; consider an analogous fix in a separate
  branch.

### Total scope

~120 LOC across 6 files + 1 plist (no new plist needed; jobs-http
already exists) + 1 install.sh edit. Primary path is 1A + 2A.

---

## Phase 19+ — Future chunks (numbered as each chunk is claimed)

Each chunk gets the next sequential Phase number when claimed.
Numbers are not pre-allocated.

## Long-term future scope (re-evaluate later)

- **Re-enable recipe consolidation as an opt-in feature** — V0 sends raw
  scaled lines per recipe (Phase 14.10). Future phase: add a `Consolidate`
  checkbox on the Recipes tab; when set, call
  `meal_planner.consolidation.consolidate_for_grocery` with proper success
  indication, quota awareness, and partial-failure UX. Side-fix the
  `if resp` `Response.__bool__` bug in `consolidation.py:77-83` at the same
  time (prints `Gemini HTTP ?: <empty>` for 4xx/5xx because `if resp` returns
  False for non-2xx; should print `resp.status_code` and `resp.text[:200]`
  unconditionally).
- **Job priority tiers (huey queue overhaul)** — Surfaced 2026-05-05 when
  a meal-planner test job sat behind a `nas_intake_scan` (~360s) on a
  single-worker consumer. User-initiated jobs should not wait minutes
  behind background scans. Three tiers to introduce:
  - **Highest / preempt** — interrupts whatever is running and executes
    the desired job immediately. Reserved for user-initiated foreground
    actions (e.g. `meal_planner_send_to_todoist`,
    `meal_planner_clear_todoist`, dispatcher commands). Implementation
    likely needs a second worker or a cooperative-cancel hook in
    long-running kinds — huey doesn't preempt natively.
  - **High / jump-to-front** — does not interrupt the current task but
    moves to position 0 of pending so it runs the moment Worker-1 frees
    up. Good fit for chat-triggered jobs that are tolerant of seconds-
    not-minutes of latency.
  - **Always-last / starvable** — continuously bumped to the bottom of
    pending as long as anything else is queued. Fits jobs that should
    only run when the system is otherwise idle (deep NAS scans, large
    photo OCR backfills, restic prune). Implies the consumer needs to
    re-rank pending on each pop, not just FIFO drain.
  Map every existing kind to a tier as part of the phase. Open question:
  is this a huey configuration change (priorities + multiple workers),
  a custom dispatcher in front of huey, or a switch to a different queue
  backend? Decide during the phase.
- **Tier-2 LLM orchestrator** — design at `future-architecture-upgrade.md`.
  CEO-approved 2026-04-30 but **demoted to long-term scope on 2026-05-01.**
  Phase 12's `Job` framework already absorbs most of its plumbing (typed
  queue, single worker, audit log, console surface, recipe registry).
  Re-evaluate after the meal-planner work ships — an orchestrator on top
  of the Jobs framework may still make sense, or the Jobs framework alone
  may be sufficient. Don't pre-build.
- **BlueBubbles iMessage bridge** — requires iCloud sign-in on the mini.
  Defer until we actually want iMessage-based control.
- **Hermes Agent / OpenClaw evaluation** — couldn't verify OpenClaw in 2026
  web searches; both need real-world provenance audit before installing.
  Finance / dispatcher / event-aggregator work fine without an agent framework.
- **Brainstorm backlog (suggestions, no fixed ranking)** —
  `~/.claude/plans/come-up-with-more-encapsulated-spring.md` carries ~55
  ideas grouped by domain. Examples: receipt → YNAB matcher, morning
  brief, document Q&A, trip detector, anomaly digest, relationship radar,
  cross-corpus Recall search. None are committed scope; the user picks
  one in context when ready and it becomes a Phase at that moment.

---

## Reference

- `Mac-mini/README.md` — current state, running services, key decisions
- `Mac-mini/PHASE6.md` — Phase 6 operator runbook
- `Mac-mini/history/` — completed-phase porting recipes
- `~/.claude/plans/i-want-you-to-tranquil-pearl.md` — frozen initial setup
  plan (phases 0–7 as originally scoped); preserved for history
- Memory entries to pull context from at session start:
  - `reference_mac_mini_porting_checklist.md` — **start here** when adding
    a new project on the mini; reproducible order-of-ops
  - `project_mac_mini_keychain_shim.md` — empty-password login keychain +
    `KEYCHAIN_PATH` env var + keyring shim pattern
  - `feedback_macos_afw_python.md` — allow Python through AFW before any
    non-loopback bind or you'll chase a phantom "app is broken" bug
  - `project_mac_mini_path_cleanup.md` — sed rewrites + pycache gotcha +
    the safe `git pull` pattern for the mini's mutated working tree
  - `feedback_macos_tcc_avoid_protected_paths.md` — why code lives at
    `~/Home-Tools`, not `~/Documents`
  - `feedback_mac_mini_readme_upkeep.md` — keep README in sync
  - `project_health_dashboard.md` — current state of the dashboard on
    the mini
  - `project_event_aggregator.md` / `project_setup_state.md` — what the
    event-aggregator expects
  - `feedback_privacy.md` + `feedback_mock_dryrun.md` — never run real data
    through Claude; always `--mock --dry-run`

---

## How to pick up next session

Paste into the opening prompt something like:

> Read `Mac-mini/PLAN.md` and `Mac-mini/README.md` in this repo, then let's
> continue the Mac mini build from where we left off. Next up is Phase 7
> (NAS backup).

That's enough context — the plan points at the memory files and the README,
so Claude will pick up from there.
