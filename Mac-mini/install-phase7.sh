#!/usr/bin/env bash
# install-phase7.sh — install Phase 7 NAS backup (restic, two repos).
#
# Two-phase installer because of the 1Password copy step:
#
#   bash Mac-mini/install-phase7.sh
#     - installs restic (brew)
#     - generates 2 random passwords
#     - reads NAS SMB creds from event-aggregator/.env
#     - stores both restic passwords in login keychain
#     - writes ~/recovery-secrets.txt (mode 600) with all 5 fields
#     - prints ACTION REQUIRED + exits 0
#     - YOU: copy 5 fields into 1Password, rm the file
#
#   bash Mac-mini/install-phase7.sh --finalize
#     - verifies recovery-secrets.txt was deleted (proves you saved it)
#     - initializes both restic repos
#     - copies + loads 3 LaunchAgent plists
#     - runs first hourly + first daily backup as smoke
#     - prints status + how to run test-phase7.sh
#
# Idempotent on both phases. Mirrors install-phase6.sh.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$HERE/scripts"
PLISTS_DIR="$HERE/LaunchAgents"
LA_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/home-tools"
RUN_DIR="$HOME/Home-Tools/run"
LOGS_DIR="$HOME/Home-Tools/logs"
BACKUP_ROOT="$HOME/Share1/mac-mini-backups"
KEYCHAIN_PATH="$HOME/Library/Keychains/login.keychain-db"
ENV_FILE="$HOME/Home-Tools/event-aggregator/.env"
SECRETS_FILE="$HOME/recovery-secrets.txt"

PLISTS=(
  com.home-tools.restic-hourly
  com.home-tools.restic-daily
  com.home-tools.restic-prune
)

# ── Phase selector ────────────────────────────────────────────────────
FINALIZE=0
if [ "${1:-}" = "--finalize" ]; then
  FINALIZE=1
fi

# ── Common pre-flight checks ──────────────────────────────────────────
echo "== Phase 7 install (finalize=$FINALIZE) =="
echo "  source: $HERE"

if [[ ! -d "$SCRIPTS_DIR" || ! -d "$PLISTS_DIR" ]]; then
  echo "ERROR: missing $SCRIPTS_DIR or $PLISTS_DIR" >&2
  exit 1
fi

for f in restic-backup.py restic-prune.py restic-restore-test.py restic-bare-metal-restore.sh; do
  if [[ ! -f "$SCRIPTS_DIR/$f" ]]; then
    echo "ERROR: missing $SCRIPTS_DIR/$f" >&2
    exit 1
  fi
done

if [[ "$FINALIZE" = "0" ]]; then
  # ════════════════════════════════════════════════════════════════════
  # Phase 1 — prepare
  # ════════════════════════════════════════════════════════════════════

  # 1.1 — restic installed?
  if ! command -v restic >/dev/null 2>&1; then
    echo "[1/7] installing restic via brew"
    if ! command -v brew >/dev/null 2>&1; then
      echo "ERROR: brew not found. Install Homebrew first." >&2
      exit 1
    fi
    brew install restic
  else
    echo "[1/7] restic already installed: $(restic version | head -1)"
  fi

  # 1.2 — NAS reachable?
  if [[ ! -d "$HOME/Share1" ]] || ! ls "$HOME/Share1" >/dev/null 2>&1; then
    echo "[2/7] NAS not reachable, attempting mount-nas.sh"
    if [[ -x "$SCRIPTS_DIR/mount-nas.sh" ]]; then
      bash "$SCRIPTS_DIR/mount-nas.sh"
    else
      echo "ERROR: $SCRIPTS_DIR/mount-nas.sh not executable, cannot mount NAS" >&2
      exit 1
    fi
  else
    echo "[2/7] NAS mounted at $HOME/Share1"
  fi

  if [[ ! -d "$BACKUP_ROOT" ]]; then
    echo "ERROR: $BACKUP_ROOT does not exist on Share1. Create the folder on the NAS first." >&2
    exit 1
  fi

  # 1.3 — Read NAS creds.
  if [[ ! -r "$ENV_FILE" ]]; then
    echo "ERROR: cannot read $ENV_FILE (need NAS_USER, NAS_PASSWORD, NAS_DHCP_IPADDRESS)" >&2
    exit 1
  fi
  NAS_USER="$(grep -E '^NAS_USER=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  NAS_PASSWORD="$(grep -E '^NAS_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  NAS_IP="$(grep -E '^NAS_DHCP_IPADDRESS=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  if [[ -z "$NAS_USER" || -z "$NAS_PASSWORD" || -z "$NAS_IP" ]]; then
    echo "ERROR: missing one of NAS_USER, NAS_PASSWORD, NAS_DHCP_IPADDRESS in $ENV_FILE" >&2
    exit 1
  fi
  echo "[3/7] read NAS creds from $ENV_FILE (user=$NAS_USER ip=$NAS_IP)"

  # 1.4 — Generate 2 restic passwords (or reuse if already present).
  HOURLY_PW="$(security find-generic-password -s restic-hourly-backup -a password -w "$KEYCHAIN_PATH" 2>/dev/null || echo '')"
  DAILY_PW="$(security find-generic-password -s restic-daily-backup -a password -w "$KEYCHAIN_PATH" 2>/dev/null || echo '')"

  if [[ -z "$HOURLY_PW" ]]; then
    HOURLY_PW="$(openssl rand -base64 32)"
    security add-generic-password -U -s restic-hourly-backup -a password -w "$HOURLY_PW" "$KEYCHAIN_PATH"
    echo "[4/7] generated and stored restic-hourly-backup password"
  else
    echo "[4/7] restic-hourly-backup password already in keychain (reusing)"
  fi

  if [[ -z "$DAILY_PW" ]]; then
    DAILY_PW="$(openssl rand -base64 32)"
    security add-generic-password -U -s restic-daily-backup -a password -w "$DAILY_PW" "$KEYCHAIN_PATH"
    echo "[5/7] generated and stored restic-daily-backup password"
  else
    echo "[5/7] restic-daily-backup password already in keychain (reusing)"
  fi

  # 1.5 — Write secrets file.
  umask 077
  cat > "$SECRETS_FILE" << EOF
================================================================
  Mac mini home server — recovery secrets
  Captured: $(date -u +%Y-%m-%dT%H:%M:%SZ)

  COPY ALL 5 FIELDS INTO A NEW 1Password SECURE NOTE.
  Suggested title: "Mac mini home server recovery"
  Then delete this file: rm $SECRETS_FILE
================================================================

  1. restic hourly password:    $HOURLY_PW
  2. restic daily password:     $DAILY_PW
  3. NAS SMB user:              $NAS_USER
  4. NAS SMB password:          $NAS_PASSWORD
  5. NAS IP:                    $NAS_IP

  Optional: print a paper copy, store in a fire safe / filing cabinet.
================================================================
EOF
  chmod 600 "$SECRETS_FILE"
  echo "[6/7] wrote $SECRETS_FILE (mode 600)"

  # 1.6 — Print ACTION REQUIRED.
  echo
  echo "================================================================"
  echo "  ACTION REQUIRED — do this now:"
  echo "================================================================"
  echo "  1. cat $SECRETS_FILE"
  echo "  2. Open 1Password, create Secure Note 'Mac mini home server recovery'"
  echo "  3. Paste in all 5 fields, save"
  echo "  4. (optional) print a paper copy"
  echo "  5. Delete the file: rm $SECRETS_FILE"
  echo "  6. Re-run this installer with --finalize:"
  echo "        bash $0 --finalize"
  echo "================================================================"
  echo
  echo "[7/7] PHASE 1 COMPLETE — repos NOT yet initialized, agents NOT yet loaded."
  echo "      Re-run with --finalize after copying secrets to 1Password."
  exit 0
fi

# ════════════════════════════════════════════════════════════════════
# Phase 2 — finalize
# ════════════════════════════════════════════════════════════════════

# 2.1 — User must have deleted the secrets file.
if [[ -f "$SECRETS_FILE" ]]; then
  echo "ERROR: $SECRETS_FILE still exists." >&2
  echo "       This means you haven't copied the secrets to 1Password yet." >&2
  echo "       After copying, run: rm $SECRETS_FILE" >&2
  echo "       Then re-run: bash $0 --finalize" >&2
  exit 1
fi
echo "[1/8] confirmed $SECRETS_FILE was deleted (you copied secrets to 1Password)"

# 2.2 — Verify both keychain entries are still there.
HOURLY_PW="$(security find-generic-password -s restic-hourly-backup -a password -w "$KEYCHAIN_PATH" 2>/dev/null || echo '')"
DAILY_PW="$(security find-generic-password -s restic-daily-backup -a password -w "$KEYCHAIN_PATH" 2>/dev/null || echo '')"
if [[ -z "$HOURLY_PW" || -z "$DAILY_PW" ]]; then
  echo "ERROR: keychain missing restic-hourly-backup or restic-daily-backup." >&2
  echo "       Re-run the prepare phase: bash $0" >&2
  exit 1
fi
echo "[2/8] verified both restic keychain entries"

# 2.3 — NAS reachable + mac-mini-backups exists.
if [[ ! -d "$BACKUP_ROOT" ]]; then
  echo "ERROR: $BACKUP_ROOT not found. Mount the NAS and create the folder." >&2
  exit 1
fi
echo "[3/8] NAS reachable, $BACKUP_ROOT exists"

# 2.4 — Make scripts executable.
chmod +x "$SCRIPTS_DIR/restic-backup.py"
chmod +x "$SCRIPTS_DIR/restic-prune.py"
chmod +x "$SCRIPTS_DIR/restic-restore-test.py"
chmod +x "$SCRIPTS_DIR/restic-bare-metal-restore.sh"
echo "[4/8] scripts are executable"

# 2.5 — Create state + log dirs.
mkdir -p "$LA_DIR" "$LOG_DIR" "$RUN_DIR" "$LOGS_DIR"

# 2.6 — Initialize both repos (idempotent: skip if already done).
HOURLY_REPO="$BACKUP_ROOT/restic-hourly"
DAILY_REPO="$BACKUP_ROOT/restic-daily"

if [[ -f "$HOURLY_REPO/config" ]]; then
  echo "[5a/8] hourly repo already initialized at $HOURLY_REPO"
else
  echo "[5a/8] initializing hourly repo at $HOURLY_REPO"
  RESTIC_REPOSITORY="$HOURLY_REPO" RESTIC_PASSWORD="$HOURLY_PW" restic init
fi
if [[ -f "$DAILY_REPO/config" ]]; then
  echo "[5b/8] daily repo already initialized at $DAILY_REPO"
else
  echo "[5b/8] initializing daily repo at $DAILY_REPO"
  RESTIC_REPOSITORY="$DAILY_REPO" RESTIC_PASSWORD="$DAILY_PW" restic init
fi

# 2.7 — Run first backups BEFORE loading the heartbeat probe to avoid
#       Day-1 stale-flag noise.
echo "[6a/8] first hourly backup"
KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$SCRIPTS_DIR/restic-backup.py" --profile hourly || {
  echo "ERROR: first hourly backup failed; check $LOG_DIR/restic-hourly.log" >&2
  exit 1
}
echo "[6b/8] first daily backup"
KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$SCRIPTS_DIR/restic-backup.py" --profile daily || {
  echo "ERROR: first daily backup failed; check $LOG_DIR/restic-daily.log" >&2
  exit 1
}

# 2.8 — Install / reinstall each plist.
for label in "${PLISTS[@]}"; do
  src="$PLISTS_DIR/$label.plist"
  dst="$LA_DIR/$label.plist"

  if [[ ! -f "$src" ]]; then
    echo "ERROR: missing $src" >&2
    exit 1
  fi

  if launchctl list 2>/dev/null | grep -qE "[[:space:]]${label}$"; then
    echo "[7/8] [$label] unloading previous"
    launchctl unload "$dst" 2>/dev/null || true
  fi

  echo "[7/8] [$label] installing $src -> $dst"
  cp "$src" "$dst"

  echo "[7/8] [$label] loading"
  launchctl load "$dst"
done

# Verify.
sleep 2
echo
echo "== Status =="
for label in "${PLISTS[@]}"; do
  line=$(launchctl list 2>/dev/null | grep -E "[[:space:]]${label}$" || true)
  if [[ -n "$line" ]]; then
    echo "  $line"
  else
    echo "  $label  NOT LISTED"
  fi
done

echo
echo "[8/8] PHASE 7 COMPLETE"
echo "Verify with:"
echo "  ls -la $LA_DIR/com.home-tools.restic-{hourly,daily,prune}.plist"
echo "  tail -20 $LOG_DIR/restic-hourly.log"
echo "  python3 $SCRIPTS_DIR/restic-restore-test.py"
echo
echo "Run the 13 deploy-verification gates:"
echo "  bash $SCRIPTS_DIR/test-phase7.sh --all"
echo
echo "Confirm zero LaunchAgent drift:"
echo "  python3 $SCRIPTS_DIR/preflight.py"
echo
echo "Rollback (if needed):"
for label in "${PLISTS[@]}"; do
  echo "  launchctl unload $LA_DIR/$label.plist && rm $LA_DIR/$label.plist"
done
echo "  # Repos themselves are at $BACKUP_ROOT — leave them or remove with: rm -rf $BACKUP_ROOT/restic-{hourly,daily}"
echo
echo "REMINDER: clear your terminal scrollback with Cmd+K so the secrets don't sit in your buffer."
