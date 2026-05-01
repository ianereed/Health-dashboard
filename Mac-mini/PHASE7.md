# Phase 7 — NAS Backup (operator runbook)

> **Status (2026-05-01):** code-only, not yet deployed. Two-phase install
> still requires the user 1Password copy step. Once deployed, this runbook
> is the authoritative operator doc.

## What it is

Two restic repos on the iananny NAS, written hourly + daily by two
LaunchAgents on the mini, pruned weekly by a third. Encrypted-by-default
via restic. Single-user, NAS-only target (no off-site this round).

```
         com.home-tools.restic-hourly  (every 1h at :17)
                       |
                       v
         restic-backup.py --profile hourly
                       |
                       v
         backs up: health.db (the load-bearing one)
                       |
                       v
         ~/Share1/mac-mini-backups/restic-hourly/

         com.home-tools.restic-daily   (03:30 daily)
                       |
                       v
         restic-backup.py --profile daily
                       |
                       v
         backs up: state.json + event_log.jsonl + .env
                   finance.db + nas-intake/state.json
                   login.keychain-db + incidents.jsonl
                       |
                       v
         ~/Share1/mac-mini-backups/restic-daily/

         com.home-tools.restic-prune   (Sun 04:00 weekly)
                       |
                       v
         restic-prune.py
                       |
                       v
         restic prune (both repos sequentially)
```

Time Machine is **not** part of v1. The 6 priority files in the daily
repo are the irreplaceable ones; everything else is reproducible from
git + brew + pip.

## Files

| Path | Purpose |
|---|---|
| `Mac-mini/scripts/restic-backup.py` | Wrapper invoked by hourly + daily LaunchAgents (`--profile {hourly,daily}`) |
| `Mac-mini/scripts/restic-prune.py` | Weekly prune for both repos |
| `Mac-mini/scripts/restic-restore-test.py` | Restore latest health.db, sha256 + `PRAGMA integrity_check` |
| `Mac-mini/scripts/restic-bare-metal-restore.sh` | Documented manual recovery walkthrough (also Gate 11) |
| `Mac-mini/LaunchAgents/com.home-tools.restic-hourly.plist` | Hourly backup, every hour at minute 17 |
| `Mac-mini/LaunchAgents/com.home-tools.restic-daily.plist` | Daily backup, 03:30 |
| `Mac-mini/LaunchAgents/com.home-tools.restic-prune.plist` | Weekly prune, Sun 04:00 |
| `Mac-mini/install-phase7.sh` | Two-phase installer (`--finalize` for second phase) |
| `Mac-mini/scripts/test-phase7.sh` | 13 deploy verification gates |
| `Mac-mini/RECOVERY.md` | Bare-metal recovery doc (no secrets; points at 1Password) |

## State files

| Path | Owner | Purpose |
|---|---|---|
| `~/Home-Tools/run/restic-{hourly,daily}-state.json` | restic-backup.py | Debouncing counters: `{observed, consecutive, emitted}` |
| `~/Home-Tools/run/restic-{hourly,daily}-failed.flag` | restic-backup.py | Marker written on persistent failure, cleared on next success |
| `~/Library/Logs/home-tools/restic-{hourly,daily,prune}.log` | launchd | stdout+stderr |
| `~/Home-Tools/logs/incidents.jsonl` | restic-backup.py (debounced state changes only) + heartbeat (backup_health probe) | Phase 6 daily-digest reads this |

## Install

**Phase 1 (prepare):**

```bash
ssh homeserver@homeserver
cd ~/Home-Tools
git pull
bash Mac-mini/install-phase7.sh
```

The installer:
1. Brews restic (if missing)
2. Verifies NAS reachable + `~/Share1/mac-mini-backups/` exists
3. Reads NAS SMB creds from `event-aggregator/.env`
4. Generates 2 random passwords (`openssl rand -base64 32`)
5. Stores both in the login keychain
6. Writes `~/recovery-secrets.txt` (mode 600) with all 5 fields
7. Prints **ACTION REQUIRED** + exits

**You then:**
- `cat ~/recovery-secrets.txt`
- Open 1Password, create Secure Note "Mac mini home server recovery"
- Paste in 5 fields (2 restic passwords + 3 NAS SMB fields), save
- Optionally print a paper copy
- `rm ~/recovery-secrets.txt`

**Phase 2 (finalize):**

```bash
bash Mac-mini/install-phase7.sh --finalize
```

The installer:
1. Verifies `recovery-secrets.txt` was deleted (proves you saved it)
2. Verifies both keychain entries are still present
3. Initializes both restic repos (idempotent — skips if already initialized)
4. Runs first hourly + first daily backups as smoke test
5. Copies + loads 3 LaunchAgent plists
6. Prints status, test command, rollback command

## Deploy verification

```bash
bash Mac-mini/scripts/test-phase7.sh --all
```

13 gates. Some take a few seconds (SQLite + SMB I/O). Total ~3 minutes.

Then:

```bash
python3 Mac-mini/scripts/preflight.py
# expect: 18 services (was 15) — added restic_hourly, restic_daily, restic_prune
```

## Recovery

See `Mac-mini/RECOVERY.md`. The TL;DR:

- 1Password Secure Note "Mac mini home server recovery" has 5 fields
- On a clean mini: `brew install restic`, mount NAS, run
  `Mac-mini/scripts/restic-bare-metal-restore.sh` interactively

## Daily life

The system is silent on the happy path. You'll see:
- One Phase 6 daily-digest in Slack at 07:00 each day. If a backup ran
  successfully or the prior fail->ok transition happened, it shows up.
  Otherwise there's no backup-related noise.
- The service-monitor dashboard at `homeserver:8502/` shows backup lane
  status (3 agents, last-fire timestamp, last-exit code).

## Failure modes (what you'll see)

| Symptom | Diagnosis | Recovery |
|---|---|---|
| Daily digest mentions `backup:hourly` flipped to `fail` | NAS unreachable persistently OR repo corrupt OR keychain lookup failed | Check `~/Library/Logs/home-tools/restic-hourly.log` and `~/Home-Tools/run/restic-hourly-failed.flag` for the reason. If `nas_unreachable`: run `bash Mac-mini/scripts/mount-nas.sh`. If `repo_corrupt`: see "Repo corrupt" below. If `keychain`: re-run `security unlock-keychain -p ""`. |
| Heartbeat probe says `backup:hourly` is stale (>2h) | Hourly agent didn't fire | `launchctl list \| grep restic`, `tail /tmp/com.home-tools.restic-hourly.out` (if exists), check launchd loaded the plist |
| `repo_corrupt` incident kind | `~/Share1/mac-mini-backups/restic-{hourly,daily}/` has `config` but no `keys/` (or vice versa) | Investigate by hand; do NOT auto-init (would lose history). May need to restore the repo from a sibling backup or accept history loss and re-init from scratch. |
| Test gate 9 (concurrent write) fails integrity_check | Restic+SQLite WAL captured an inconsistent state — should be very rare | One-off: re-run gate 9. If recurring: switch to `sqlite3 .backup` semantics in restic-backup.py before calling restic. |

## Rollback

```bash
for label in com.home-tools.restic-hourly com.home-tools.restic-daily com.home-tools.restic-prune; do
  launchctl unload ~/Library/LaunchAgents/${label}.plist
  rm ~/Library/LaunchAgents/${label}.plist
done

# Optional — leave the repos in place (they're useful as-is for restore-only mode)
# Or wipe them:
# rm -rf ~/Share1/mac-mini-backups/restic-hourly ~/Share1/mac-mini-backups/restic-daily

# Optional — remove keychain entries:
# security delete-generic-password -s restic-hourly-backup -a password
# security delete-generic-password -s restic-daily-backup -a password
```

## Future work (not in v1)

- **Phase 7.5 (off-site leg)**: B2/Wasabi as a second restic repo. Add when something concrete makes it feel necessary.
- **Phase 7.5 (Time Machine via USB SSD)**: ~$50 SSD plugged into the mini, GUI checkbox for encryption. Provides system-native restore experience. Add when the mini sees a screen for some other reason.
- **Restic password rotation**: TODO entry if a real rotation event occurs. `restic key passwd` exists but the operator path needs scripting.
- **Weekly automated restore probe**: scheduled `restic-restore-test.py` if a silent-restore-fail incident ever occurs.
