# Phase 12 hotfix — fix plan

> **Scope:** repair the cutover that auto-rolled back 11/12 migrations on
> 2026-05-01. Stay within Phase 12 (no new phase number per the
> no-decimals rule). Goal: re-cutover successfully, get to a clean
> 72h soak.

## Diagnosis (verified live, 2026-05-01)

11 of 12 migrations rolled back at the verifier's first cycle. After
running the failing kinds manually with the consumer's exact subprocess
command, the failures group into four clusters:

### Cluster A — wrapper bugs

| Kind | Bug | Fix |
|---|---|---|
| `finance_monitor_watch` | Wraps `finance-monitor/watcher.py` but original plist runs `main.py watch`. Also uses `sys.executable` (consumer venv) instead of project venv → `dotenv` import fails. No `cwd=`. | Match original plist: `[finance-monitor/.venv/bin/python3, finance-monitor/main.py, watch]` with `cwd=finance-monitor/`. |
| `heartbeat` | Uses `sys.executable`. Original used `/usr/bin/python3`. Stdlib-only script, so this WORKS — but the baseline metric is fundamentally wrong (see Cluster C). | Optional: switch to system python for parity. Keep wrapper as-is; fix baseline metric instead. |

Other wrappers (`daily_digest`, `weekly_ssh_digest`, `dispatcher_3day_check`, `restic_*`, `nas_intake_scan`) use scripts that
either are stdlib-only Python or are bash wrappers — they run fine. The
manual verification confirms `nas_intake_scan` actually succeeds end-to-end.

### Cluster B — pre-existing brokenness, NOT migration's fault

`health_intervals_poll` raises `RuntimeError: Intervals.icu credentials
not found in keychain`. The original `com.health-dashboard.intervals-poll`
plist uses identical args (`python -m collectors.intervals_collector
--days 14`, `cwd=health-dashboard/`) — the keychain entries
`home-tools / intervals_api_key` and `intervals_athlete_id` simply do
not exist on this machine. Verified via:

```
$ security find-generic-password -a 'home-tools' -s 'intervals_api_key'
security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.
```

This kind has been silently failing on the original LaunchAgent for
some time. The migration revealed it; the migration is not the cause.

**Decision:** do not migrate `health_intervals_poll` until credentials
are populated. The migrate-all script in `jobs/install.sh` should skip
kinds whose `@requires` declarations fail, OR we hold back this kind
manually.

`health_collect`: same ambient question. Need to verify health.db is
actually being updated by some other source (dashboard receiver at :8095
posts iPhone data, but the collector itself fetches Garmin/Strava). The
fact that health.db mtime is hours stale on a quiet machine is normal,
not an artifact of the migration. Recommend: hold back `health_collect`
until we audit whether it's actually doing useful work, OR widen its
divergence window to 25h (it fires twice daily at 07:00 + 07:20, so 35m
window is plausible only on a fresh-data day).

`health_staleness`: rc=1 under consumer but rc=0 manually. Both runs
use same args + cwd. The 0.207s exit before any output suggests the
script crashed before reaching its print statements — possibly a race
on the SQLite WAL or a truncated stderr. Holding judgement; will
re-run under the consumer post-restart and look at full traceback
without the `:200` truncation.

### Cluster C — verifier policy bugs

Three independent issues in `migration_verifier.py`:

1. **`path_missing` ignores `divergence_window`.** A kind whose baseline
   is `file-mtime:logs/weekly-ssh-digest.log` and cadence is weekly
   (Mon 09:00) has its first natural fire days away. At T+36min the
   log file doesn't exist yet → `_check_mtime_recent` returns `False`
   immediately → rollback. The 80h / 25h / 8d windows declared in the
   kinds are silently ignored on this branch.

   **Fix:** in `check_baseline`, when path is missing, return
   `(False, evidence)` only when the migration has been in flight long
   enough that a fire SHOULD have produced the file. Pass
   `started_at` + `cadence_seconds` into the check.

2. **No baseline snapshot at `migration_begun`.** The verifier compares
   current baseline value to "now". For mtime-based metrics, this means
   a STALE pre-cutover file looks identical to a STALE post-cutover
   file. We can't tell whether the migration is failing or whether the
   file was already old.

   **Fix:** in `_migrate()` (cli.py), capture the current baseline
   value at migration begin (`mtime` for file/db metrics, `count` for
   restic). The verifier requires the value to ADVANCE before promoting,
   not just be "fresh". This handles the case where `health_intervals_poll`
   was always producing stale data — its migration will correctly
   roll back NOT because the kind broke, but because the baseline
   never advances. (And for kinds that genuinely advance, the verifier
   still works.)

3. **`heartbeat`'s baseline is fundamentally wrong.** Heartbeat only
   writes to `incidents.jsonl` on STATE CHANGES (per its docstring +
   confirmed by reading the script). A 35m window assumes a write
   every 35 min, but a healthy steady-state mini might go hours
   without state changes. The verifier rolled heartbeat back at hour 1
   because incidents.jsonl was 60min old — totally normal.

   **Fix:** change heartbeat's baseline to `file-mtime:run/heartbeat-state.json`
   (the script writes this every fire, not just on state changes). Window
   stays 35m.

### Cluster D — restic baseline paths

`_check_restic_snapshot_count` in `migration_verifier.py:104` looks at
`Path.home() / "Share1" / repo` — i.e. `~/Share1/restic-hourly`.
Verified actual paths: `~/Share1/mac-mini-backups/restic-{hourly,daily}`
(per `Mac-mini/scripts/restic-backup.py:25`,
`BACKUP_ROOT = HOME / "Share1" / "mac-mini-backups"`).

**Fix:** change verifier's path computation to
`Path.home() / "Share1" / "mac-mini-backups" / repo`. Also: the
function checks for env var `RESTIC_PASSWORD_RESTIC_HOURLY` which
should exist (consumer wrapper exports it from keychain). Verify
in the post-deploy smoke test.

`restic_prune` baseline `file-mtime:logs/restic-prune.log` — the log
gets created by the prune script on first run. With the Cluster C #1
fix, this becomes a non-issue (8d window will be honored on path-missing).

## Fix list — code changes

### `jobs/kinds/finance_monitor_watch.py`
```python
PROJECT = Path(__file__).resolve().parents[2] / "finance-monitor"
VENV_PYTHON = PROJECT / ".venv" / "bin" / "python3"

@huey.periodic_task(crontab(minute="*/5"))
@requires(["db:finance-monitor/data/finance.db", "fs:finance-monitor"])
@baseline(metric="db-mtime:finance-monitor/data/finance.db", divergence_window="6m")
@migrates_from("com.home-tools.finance-monitor-watcher")
def finance_monitor_watch() -> dict:
    proc = subprocess.run(
        [str(VENV_PYTHON), "main.py", "watch"],
        cwd=str(PROJECT), capture_output=True, text=True, timeout=240,
    )
    ...
```

### `jobs/kinds/heartbeat.py`
```python
@baseline(metric="file-mtime:run/heartbeat-state.json", divergence_window="35m")
```

### `jobs/kinds/_internal/migration_verifier.py`
1. Add `cadence_seconds` + `started_at` to `check_baseline` signature.
2. Add `baseline_snapshot` dict to migration record.
3. In path_missing branch: if elapsed since started_at < `cadence_seconds * 2`,
   return `(True, {"reason": "first_fire_grace"})` — counts as healthy
   but does NOT increment `hours_soaked`.
4. For non-snapshot-comparing checks (mtime), require `current > snapshot`.
5. `_check_restic_snapshot_count`: change repo_path computation to
   `Path.home() / "Share1" / "mac-mini-backups" / repo`.

### `jobs/cli.py` (`_migrate` function)
1. After computing `bl`, call a new helper `_capture_baseline_snapshot(bl)`
   that returns the current baseline value (mtime/count/None for unsupported).
2. Add `"baseline_snapshot": <value>` to the migration record.

### Holdouts (do NOT auto-migrate)
- `health_intervals_poll` — until keychain credentials populated.
- `health_collect` — until we verify it's actually doing useful work.
- `health_staleness` — until we observe its consumer-side rc=1 with
  full traceback.

## Tests to add

`jobs/tests/test_migration_verifier.py`:
- `test_path_missing_within_grace_period_passes`: kind with cadence=86400
  and started 1h ago, baseline file missing → verifier returns "ran",
  hours_soaked unchanged, NOT rolled back.
- `test_path_missing_after_grace_period_rolls_back`: cadence=300, started
  3h ago, baseline file missing → rolled back.
- `test_baseline_snapshot_advance_required`: snapshot mtime = T0,
  current mtime = T0 (unchanged), within window → fail (no advance).
- `test_baseline_snapshot_advance_satisfied`: snapshot mtime = T0,
  current = T0+10s, within window → pass.
- `test_restic_path_uses_mac_mini_backups`: monkeypatch home, ensure
  the function looks at `~/Share1/mac-mini-backups/<repo>`.

## Deploy plan

1. Apply code fixes locally; run `pytest jobs/tests/`.
2. Commit with descriptive message; push to main.
3. SSH to mini; `cd ~/Home-Tools && git pull`.
4. Restart consumer: `launchctl kickstart -k gui/$(id -u)/com.home-tools.jobs-consumer`.
5. Clear `~/Home-Tools/run/migrations.json` (`rolled_back` history is now
   noise from a known-bad cycle).
6. Re-cutover with the 9 healthy kinds (skip `health_intervals_poll`,
   `health_collect`, `health_staleness` until those questions are
   resolved). Use `bash jobs/install.sh migrate-all` IF that script
   skips on `@requires` failure, otherwise migrate one at a time.
7. Wait for next verifier cycle (next `:03` past the hour). Verify all
   9 still in_flight, no rollbacks.
8. Update memory + journal. Set Mon 2026-05-04 calendar reminder
   description to the new soak end time.
