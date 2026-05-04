# Phase 12 — Mini Jobs framework + Mini Ops console (operator runbook)

> **Status (2026-05-01):** code shipped; deployment + cutover pending.
> Once deployed, this runbook is the authoritative operator doc.

## What it is

A single typed-job framework that replaces 12 of the mini's 21 LaunchAgents
with `@huey.periodic_task` definitions in `jobs/kinds/*.py`. The huey
consumer is one process (one plist), so launchd has 9 fewer agents to
orchestrate.

```
                       Apple Shortcut    Claude session
                                \           /
                                 v         v
                          jobs-http  :8504   (token auth)
                                |
                                v
          jobs-consumer  +  huey  ←── @periodic_task
                                |
                                v
              ┌─────────────────┴─────────────────┐
              │                                   │
       12 migrated kinds              migration_verifier (hourly)
              │                                   │
       (subprocess wrapper of                  baseline checks +
        existing scripts)                      auto-rollback /
                                               auto-promote
              │
              v
       same outputs as before
       (incidents.jsonl, *.db,
        Slack messages, restic
        snapshots, NAS files…)

       Mini Ops console :8503    (Streamlit, 4 tabs + reserved Plan slot)
       Tabs (left → right):
         Jobs       — queue depth, kinds, in-flight migrations
         Decisions  — cards.jsonl feed (approve/reject)
         Ask        — local Ollama prompt
         Intake     — paste/upload to ~/nas/Intake/
         Plan       — Phase 13 placeholder
       Sidebar: Settings status panel
```

## What's where

| Path | Purpose |
|---|---|
| `jobs/__init__.py` | Single SqliteHuey instance shared by every Job kind |
| `jobs/db.py` | WAL + busy_timeout=5000 + foreign_keys=ON on `~/Home-Tools/jobs/jobs.db` |
| `jobs/lib.py` | `@requires` + `@baseline` decorators; `RequirementsNotMet` error |
| `jobs/adapters/` | `dispatch(output_config, payload)` router → slack/gcal/todoist/card/nas/sheet |
| `jobs/kinds/<name>.py` | One file per migrated agent (12 in v1) |
| `jobs/kinds/_internal/migration_verifier.py` | Hourly verifier; rolls back on divergence; promotes at 72h soak |
| `jobs/cli.py` | `enqueue / status / kinds / new / doctor / migrate / rollback / cleanup-soaked` |
| `jobs/enqueue_http.py` | stdlib http.server at :8504 (Tailscale-bound, bearer token) |
| `jobs/install.sh` | Installer for consumer + http LaunchAgents |
| `jobs/config/*.plist` | KeepAlive plists for consumer + http |
| `console/app.py` | Streamlit entry — "Mini Ops" |
| `console/tabs/{jobs,decisions,ask,intake,plan_placeholder}.py` | One module per tab |
| `console/sidebar/settings.py` | Read-only status panel |
| `console/install.sh` | Installer for console LaunchAgent |

## Migration inventory

| Kind | Cadence | `@baseline` metric | Window |
|---|---|---|---|
| heartbeat | every 30m | `incidents.jsonl-mtime` | 35m |
| daily_digest | 07:00 | `file-mtime:logs/daily-digest.log` | 20m |
| weekly_ssh_digest | Mon 09:00 | `file-mtime:logs/weekly-ssh-digest.log` | 20m |
| dispatcher_3day_check | every ~3 days | `file-mtime:logs/dispatcher-3day.txt` | 80h |
| finance_monitor_watch | every 5m | `db-mtime:finance-monitor/finance.db` | 6m |
| nas_intake_scan | every 5m | `file-mtime:nas-intake/state.json` | 6m |
| health_collect † | 07:00+07:20 | `db-mtime:health-dashboard/data/health.db` | 35m |
| health_intervals_poll † | every 5m | `db-mtime:health-dashboard/data/health.db` | 6m |
| health_staleness † | 07:00+21:00 | `file-mtime:logs/health-staleness.log` | 20m |
| restic_hourly | every :17 | `restic-snapshot-count:restic-hourly` | 80m |
| restic_daily | 03:30 | `restic-snapshot-count:restic-daily` | 25h |
| restic_prune | Sun 04:00 | `file-mtime:logs/restic-prune.log` | 8d |

**† Health migrations deferred (2026-05-04):** `health_collect`,
`health_intervals_poll`, `health_staleness` exist as huey kinds in
`jobs/kinds/` and are firing on schedule, but the formal `jobs.cli migrate`
ritual was skipped — `migrations.json` has no entry for them, the verifier
never built a baseline, and the original
`com.health-dashboard.{collect,intervals-poll,staleness}.plist` files are
unloaded but not renamed to `.disabled`. Operationally fine; bookkeeping
gap. Resume in a later phase: run `jobs.cli migrate <kind>` on each, then
`promote` (soak risk is tiny since they've been live for days).

Not migrated (still plists):

- `event-aggregator.fetch` + `event-aggregator.worker` — Phase 12.5 will
  migrate them as a unit (the worker's queue + model-swap state machine
  doesn't decouple cleanly from the fetch loop).
- `dispatcher` — KeepAlive Slack listener, not a job.
- `finance-monitor` (bot) — KeepAlive Slack listener.
- `health-dashboard.receiver` — HTTP listener at :8095.
- `health-dashboard.streamlit` — Streamlit UI at :8501.
- `service-monitor` — Streamlit UI at :8502 (this dashboard).
- `memory-tracker` / `ollama-tracker` — 1Hz samplers, not cron-shaped.

## Deploy

On the mini, after `git pull`:

```bash
# Install the framework. Bootstraps jobs/.venv, drops + loads 2 plists,
# then runs `jobs.cli doctor` to confirm the consumer answers.
bash jobs/install.sh

# Install Mini Ops console (separate venv, separate plist).
bash console/install.sh

# Cut over all 12 migrations. Each rename old plist → .plist.disabled,
# launchctl unload it, record baseline metadata in
# ~/Home-Tools/run/migrations.json.
bash jobs/install.sh migrate-all

# Verify drift checker is green.
python3 Mac-mini/scripts/preflight.py
```

After cutover, the verifier takes over. Hourly checks begin within
60 minutes (next `:03` past the hour). The new state lives in:

- `~/Home-Tools/jobs/jobs.db` (huey storage, WAL)
- `~/Home-Tools/run/migrations.json` (verifier in_flight + promoted + rolled_back)
- `~/Home-Tools/run/cards.jsonl` (decision cards feed for the console)
- `~/Home-Tools/logs/jobs-consumer.log` (consumer stdout)
- `~/Home-Tools/logs/jobs-consumer.err.log` (consumer stderr)

## Watching the soak

72 hourly successful checks → promote (delete `.plist.disabled`). Any
divergence → auto-rollback. Phase 6's daily-digest at 07:00 surfaces both
events in Slack as `migration_promoted` / `migration_rollback` incidents.

Quick checks:

```bash
# Live in-flight summary
ssh homeserver@homeserver \
  "cat ~/Home-Tools/run/migrations.json | python3 -m json.tool"

# Recent verifier activity
ssh homeserver@homeserver \
  "tail -30 ~/Home-Tools/logs/incidents.jsonl | grep migration"

# Mini Ops Jobs tab
open http://homeserver:8503/
```

## When the verifier rolls something back

The `.plist.disabled` becomes `.plist` and gets `launchctl kickstart`-ed.
The huey kind keeps running (the consumer doesn't know it was rolled
back), but the rollback logs an incident, deletes the migration from
`in_flight`, and adds it to `rolled_back`. Net: both run for a while —
which is fine because every migrated kind is idempotent in its observable
output (mtime advances, snapshot counts grow, slack posts dedup).

To make the rollback "stick" (keep the old plist running, stop the huey
kind from also running), comment out the `@huey.periodic_task` line on
the kind and redeploy the consumer. v1 doesn't have a halt-kind CLI;
that's a Phase 12.5 nice-to-have.

## When the verifier looks broken

If it's emitting spurious rollbacks:

```bash
# Halt verifier checks for one kind without rolling back
python3 -m jobs.cli halt-verifier <kind>

# That sets `halted: true` on the migration in migrations.json. Fix the
# verifier check, then edit migrations.json: set halted back to false.
```

## After all 12 promote

```bash
# Removes the .plist.disabled files for every migration in `promoted`.
# Original scripts in Mac-mini/scripts/ stay as historical reference (for
# now); a future cleanup PR can delete them.
bash jobs/install.sh cleanup-soaked
```

The verifier idles when `in_flight` is empty. It's safe to leave running;
it'll kick in again the next time `bash jobs/install.sh migrate <kind>`
adds a new migration.

## Troubleshooting

**Consumer won't start.** Check `~/Home-Tools/logs/jobs-consumer.err.log`.
Most likely: keychain not unlocked (run `security unlock-keychain -p ""
~/Library/Keychains/login.keychain-db`), or `huey_consumer.py` not on the
venv's PATH (re-run `bash jobs/install.sh`).

**HTTP 401 from :8504.** The `HOME_TOOLS_HTTP_TOKEN` environment variable
isn't set in the http LaunchAgent's audit session. The wrapper reads it
from keychain entry `home-tools/jobs_http_token` — run:

```bash
security add-generic-password -a 'home-tools' -s 'jobs_http_token' \
  -w "$(uuidgen)" ~/Library/Keychains/login.keychain-db
```

then restart the http agent: `launchctl kickstart -k gui/$(id -u)/com.home-tools.jobs-http`.

**Console returns 502.** Streamlit might still be binding (10s on cold
start). Check `~/Home-Tools/logs/console.log`. If it's stuck on Tailscale
IP detection, set `JOBS_HTTP_HOST=127.0.0.1` to force loopback temporarily.

## Out of scope (v1)

- Per-Job retry policy other than huey's default (3 retries with backoff).
  Migrations declare retries=0 implicitly via the original scripts'
  semantics; new kinds can override.
- Result lookup by id over HTTP — `/jobs/<id>` returns 501. Use the Mini
  Ops Jobs tab.
- Sheet adapter — strict NotImplementedError stub. Phase 13.
- Per-user views (Anny mode) — Phase 13's Plan tab.

---

## Phase 12.5 follow-up — Event-aggregator migration + worker retirement (2026-05-04)

Phase 12 left the event-aggregator's two LaunchAgents unmitigated. Phase
12.5–12.8b finished the migration. Summary:

### What shipped

| Phase | Commits | Description |
|-------|---------|-------------|
| 12.5 | `028dd0d` | `event_aggregator_fetch` → huey `@periodic_task` (every 10 min) |
| 12.6 | `95e3d0a` | `@requires_model` primitive in `jobs/lib.py`; worker.py shim |
| 12.7 | `0cf1b7b`, `df12304` | Worker decomposed: `event_aggregator_text`, `event_aggregator_vision`, `event_aggregator_decision_poller` kinds |
| 12.8a | `4873d8f`, `7927bf0` | 22 pre-promote bug fixes (18 from /review + 4 from independent follow-up) |
| 12.8b | `79fdfef`, `a242e30`, `748cb09` | promote subcommand, TaskWrapper fix, worker loop retired |

### Key design decisions

- **`@requires_model` primitive** (`jobs/lib.py`): process-wide singleton
  enforces serial model loading. Consumer runs `-w 1 -k thread`. A kind
  opting into concurrency must implement its own per-kind locking.
- **Transient staging queues**: `state.text_queue` / `state.ocr_queue`
  remain in state.py as staging buffers between `fetch_only()` / `enqueue-image`
  CLI and the huey task schedule. Not deprecated — load-bearing.
- **Honest soak signal**: the `record_fire("event_aggregator_text")` proxy
  in fetch was removed (12.8a Fix 7). Soak relies solely on the
  `event-aggregator-text-or-vision.last` file mtime, touched only on
  successful subprocess execution.
- **Manual promote**: the 72h soak was skipped because the proxy forged
  the signal. `python3 -m jobs.cli promote <kind>` added as a CLI command.
- **Smoke Test E finding**: `inspect.signature(TaskWrapper)` returns
  `(*args, **kwargs)` — must unwrap via `TaskWrapper.func` + `inspect.unwrap`
  to see the inner function's signature. Fixed in `jobs/cli.py:_enqueue`.

### Deferred (do not chase)

- **F**: `_load_ea_state` / `_load_ea_notifier` / `_load_ea_tz_utils`
  `exec_module` on every fire — slow leak in long-running consumer. Memoize.
- **G**: `_post_swap_decision_if_needed` cross-lock window (pre-existing 12.7).
- **H**: 3 pre-existing `test_proposals.py` failures predate this work.
