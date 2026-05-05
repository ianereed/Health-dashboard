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

**Next: Phase 15 — Recipe-photo-LLM bake-off** (research only, entry gate:
Anny's SC6 walkthrough). Ian may insert a new phase before Phase 15 — ask him
for scope before starting.

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

## Phase 15 — Recipe-photo-LLM bake-off

Research only — no production code. Compare Gemini-flash, Gemini-flash-lite,
Claude Haiku-4.5, GPT-4o-mini, local qwen2.5-vl on recipe photo extraction.
Output: `meal_planner/MODEL_CHOICE.md`.

Entry gate: Anny's Phase 14.7 walkthrough passes end-to-end (SC6).

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

Bonus side-fix surfaced by this incident: the error log line at
`consolidation.py:77-83` prints `Gemini HTTP ?: <empty>` for any 4xx/5xx
response, because `if resp` evaluates `Response.__bool__` which returns
`self.ok` (False for 4xx/5xx). Should print `resp.status_code` and
`resp.text[:200]` unconditionally. One-line fix; do whenever convenient.

## Phase 16+ — Meal-planner overhaul: build (numbered as each chunk is claimed)

Each chunk gets the next sequential Phase number when claimed.
Numbers are not pre-allocated.

## Long-term future scope (re-evaluate later)

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
