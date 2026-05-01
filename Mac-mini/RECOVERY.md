# Mac mini recovery guide

> **Read this when you've lost the mini and need to restore from scratch.**
> This file contains no secrets. The 5 secrets needed for recovery live
> in 1Password (Secure Note: "Mac mini home server recovery") and ideally
> a printed paper copy.

## What's where

| What | Where |
|---|---|
| **Encrypted backup data** | iananny NAS, SMB share Share1, folder `mac-mini-backups/` |
| **Hourly snapshots** (just `health.db`) | `~/Share1/mac-mini-backups/restic-hourly/` |
| **Daily snapshots** (the rest of the priority files) | `~/Share1/mac-mini-backups/restic-daily/` |
| **2 restic passwords** | 1Password Secure Note + offline paper copy |
| **NAS SMB user/password/IP** | 1Password Secure Note + offline paper copy |
| **The 1Password password itself** | Your head + 1Password Emergency Kit (already on Share1) |

The 5 fields in the 1Password note are:
1. restic hourly password
2. restic daily password
3. NAS SMB user
4. NAS SMB password
5. NAS IP

## Bootstrap from scratch (mini bricked, new mini in hand)

Prereqs: macOS installed on the new mini, you can ssh in, you can read
1Password from a phone or laptop.

```bash
# 1. Install Homebrew + restic + sqlite3 (sqlite3 ships with macOS but verify).
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install restic

# 2. Run the bare-metal restore walkthrough interactively.
#    (You'll need the 5 fields from 1Password — keep them in front of you.)
mkdir -p ~/Home-Tools/Mac-mini/scripts
# Either git clone the Home-Tools repo first, or copy the script in by hand:
git clone https://github.com/ianereed/Home-Tools.git ~/Home-Tools
bash ~/Home-Tools/Mac-mini/scripts/restic-bare-metal-restore.sh
```

The walkthrough prompts you for each of the 5 secrets, mounts the NAS,
restores both repos to `$HOME/restored/`, verifies `health.db` opens
and passes `PRAGMA integrity_check`. If that all succeeds:

```bash
# 3. Move restored files into place.
#    (Adjust paths if the original mini was a different macOS user.)
cp -R ~/restored/Users/homeserver/Home-Tools/* ~/Home-Tools/
cp ~/restored/Users/homeserver/Library/Keychains/login.keychain-db \
   ~/Library/Keychains/login.keychain-db

# 4. Now your keychain has the original secrets again. Re-run each project's installer:
cd ~/Home-Tools/event-aggregator && bash install_scheduler.sh
cd ~/Home-Tools/dispatcher && bash install.sh
cd ~/Home-Tools/finance-monitor && bash install.sh
cd ~/Home-Tools/health-dashboard && bash install_scheduler.sh
cd ~/Home-Tools/nas-intake && bash install.sh
cd ~/Home-Tools/service-monitor && bash install.sh
bash ~/Home-Tools/Mac-mini/install-phase6.sh

# 5. For Phase 7 itself: the backup repos already exist. Don't re-initialize.
#    Just install the LaunchAgents (skip prepare, go straight to finalize):
#      - The keychain entries restored from the daily backup, so the
#        finalize phase will find them and use them.
#      - Manually skip step 1 (--prepare) by:
#        - touch ~/recovery-secrets.txt && rm ~/recovery-secrets.txt   # satisfy the "deleted" check
#        - bash ~/Home-Tools/Mac-mini/install-phase7.sh --finalize

# 6. Verify everything's back:
python3 ~/Home-Tools/Mac-mini/scripts/preflight.py
```

## Quick scenarios

### Lost just one file (e.g., accidentally rm'd `health.db`)

```bash
# From the mini, with keychain unlocked normally:
RESTIC_REPOSITORY=~/Share1/mac-mini-backups/restic-hourly \
RESTIC_PASSWORD=$(security find-generic-password -s restic-hourly-backup -a password -w) \
restic restore latest --target /tmp/restore --include 'health.db'
# Then move /tmp/restore/Users/homeserver/Home-Tools/health-dashboard/data/health.db
# back into place (after stopping the receiver agent so it doesn't write).
```

### Lost the NAS but mini is fine

You have no backup. This is a real risk in the NAS-only design (3-2-1
not satisfied, on-LAN only). When the new NAS arrives:
1. Re-mount it at `~/Share1`
2. Re-run `bash Mac-mini/install-phase7.sh --finalize` (it'll re-init both repos from scratch — losing history but bootstrapping forward)

### Lost 1Password (forgot master password)

1Password Emergency Kit on `~/Share1/` (per the existing files there)
is your fallback. Use the Secret Key + new master password to recover.
Once 1Password is back, the 5 recovery fields are accessible again.

### Lost both 1Password AND the NAS

You restore from your printed paper copy — that's why we recommend one.
If you don't have a printed copy and lost both, the encrypted blobs on
the NAS are uncrackable without the restic passwords. Plan accordingly.

## When was the last successful backup?

```bash
# Check the heartbeat-driven incidents log.
tail -10 ~/Home-Tools/logs/incidents.jsonl | grep backup

# Or check restic directly.
RESTIC_REPOSITORY=~/Share1/mac-mini-backups/restic-hourly \
RESTIC_PASSWORD=$(security find-generic-password -s restic-hourly-backup -a password -w) \
restic snapshots --compact | tail -5
```

## What's NOT backed up (by design)

- The OS itself (macOS, brew, /Applications) — reproducible from clean install
- Project `.venv/` directories — reproducible from `requirements.txt`
- `~/.ollama/models/**` — re-pullable via `ollama pull`
- Project source code — that's what GitHub is for
- Logs — except `~/Home-Tools/logs/incidents.jsonl` which IS in the daily backup

## Maintenance reminders

- **Quarterly**: re-run `python3 Mac-mini/scripts/restic-restore-test.py` to confirm restores still work
- **Yearly**: print a fresh paper copy of the 1Password Secure Note (just in case)
- **When the NAS gets close to full**: bump retention down or archive old snapshots
