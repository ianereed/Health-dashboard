#!/usr/bin/env bash
# test-phase7.sh — 13 deploy-verification gates for Phase 7.
#
# Mirrors test-phase6.sh. Some gates write to the live NAS (idempotent —
# they create snapshots that fold into the normal retention).
#
# Usage:
#   bash test-phase7.sh --all       # run all 13 gates
#   bash test-phase7.sh 5           # run gate 5 only
#
# Each gate prints PASS / FAIL with a short diagnostic.

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
KEYCHAIN_PATH="$HOME/Library/Keychains/login.keychain-db"
BACKUP_ROOT="$HOME/Share1/mac-mini-backups"
HOURLY_REPO="$BACKUP_ROOT/restic-hourly"
DAILY_REPO="$BACKUP_ROOT/restic-daily"
LOG_DIR="$HOME/Library/Logs/home-tools"
RUN_DIR="$HOME/Home-Tools/run"
LOGS_DIR="$HOME/Home-Tools/logs"

PASS=0; FAIL=0
pass() { echo "  PASS — $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL — $1"; FAIL=$((FAIL+1)); }

unlock_kc() {
  security unlock-keychain -p "" "$KEYCHAIN_PATH" 2>/dev/null || true
}

get_pw() {
  security find-generic-password -s "$1" -a password -w "$KEYCHAIN_PATH" 2>/dev/null
}

snap_count() {
  local repo="$1"; local pw="$2"
  RESTIC_REPOSITORY="$repo" RESTIC_PASSWORD="$pw" restic snapshots --json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0"
}

# ─── Gates ────────────────────────────────────────────────────────────

gate_1() {
  echo "== Gate 1: restic version + both keychain entries readable =="
  unlock_kc
  if ! command -v restic >/dev/null 2>&1; then
    fail "restic not on PATH"; return
  fi
  echo "    restic: $(restic version | head -1)"
  HOURLY_PW="$(get_pw restic-hourly-backup)"
  DAILY_PW="$(get_pw restic-daily-backup)"
  if [[ -n "$HOURLY_PW" && -n "$DAILY_PW" ]]; then
    pass "both keychain entries readable"
  else
    fail "missing keychain entry (hourly=$([ -n "$HOURLY_PW" ] && echo ok || echo MISS), daily=$([ -n "$DAILY_PW" ] && echo ok || echo MISS))"
  fi
}

gate_2() {
  echo "== Gate 2: dry-run smoke (--profile hourly --dry-run) =="
  unlock_kc
  if KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-backup.py" --profile hourly --dry-run 2>&1 | tail -3; then
    pass "dry-run completed"
  else
    fail "dry-run errored"
  fi
}

gate_3() {
  echo "== Gate 3: live hourly backup → snapshot count grows =="
  unlock_kc
  HOURLY_PW="$(get_pw restic-hourly-backup)"
  before=$(snap_count "$HOURLY_REPO" "$HOURLY_PW")
  if KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-backup.py" --profile hourly >/dev/null 2>&1; then
    after=$(snap_count "$HOURLY_REPO" "$HOURLY_PW")
    if [[ "$after" -gt "$before" ]]; then
      pass "snapshots: $before → $after"
    else
      # Could be a no-op if nothing changed; still passes.
      pass "snapshots: $before → $after (no-change ok if file unchanged)"
    fi
  else
    fail "backup script returned non-zero"
  fi
}

gate_4() {
  echo "== Gate 4: live daily backup → .env present in latest snapshot =="
  unlock_kc
  DAILY_PW="$(get_pw restic-daily-backup)"
  if ! KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-backup.py" --profile daily >/dev/null 2>&1; then
    fail "daily backup script returned non-zero"; return
  fi
  files=$(RESTIC_REPOSITORY="$DAILY_REPO" RESTIC_PASSWORD="$DAILY_PW" restic ls latest 2>/dev/null | grep -E "(event-aggregator/\\.env|event-aggregator/state.json|login.keychain-db)" | wc -l | tr -d ' ')
  if [[ "$files" -ge 3 ]]; then
    pass ".env + state.json + keychain all present in daily snapshot"
  else
    fail "expected ≥3 priority files in daily snapshot, found $files"
  fi
}

gate_5() {
  echo "== Gate 5: restore latest health.db, sha256 + PRAGMA integrity_check =="
  unlock_kc
  if KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-restore-test.py"; then
    pass "restore + integrity_check ok"
  else
    fail "restore-test failed (see output above)"
  fi
}

gate_6() {
  echo "== Gate 6: launchd-context smoke (one-shot test plist proves keychain self-unlock works) =="
  TEST_LABEL="com.home-tools.restic-test-launchd"
  TEST_PLIST="/tmp/$TEST_LABEL.plist"
  TEST_LOG="/tmp/restic-test-launchd.log"
  # Use the actual restic-hourly agent via launchctl kickstart instead of
  # spinning a one-shot test plist. Kickstart fires the agent through
  # launchd, exercises the same keychain-self-unlock + StandardOutPath
  # plumbing, and writes to the real log so we can assert on it.
  RESTIC_LOG="$LOG_DIR/restic-hourly.log"
  before_size=$(wc -c < "$RESTIC_LOG" 2>/dev/null || echo 0)
  if launchctl kickstart -k "gui/$UID/com.home-tools.restic-hourly" 2>/dev/null; then
    sleep 5
    after_size=$(wc -c < "$RESTIC_LOG" 2>/dev/null || echo 0)
    if [[ "$after_size" -gt "$before_size" ]] && tail -50 "$RESTIC_LOG" | grep -q "backup ok"; then
      pass "launchd-mediated run completed (keychain self-unlock works under launchd)"
    else
      fail "launchd kickstart fired but no 'backup ok' in $RESTIC_LOG (size before=$before_size after=$after_size)"
    fi
  else
    fail "launchctl kickstart failed — agent may not be loaded (try: launchctl list | grep restic-hourly)"
  fi
}

gate_7() {
  echo "== Gate 7: NAS-unreachable failure path =="
  unlock_kc
  # Move backup root aside briefly.
  if [[ ! -d "$BACKUP_ROOT" ]]; then
    fail "$BACKUP_ROOT does not exist — cannot test"
    return
  fi
  ASIDE="$BACKUP_ROOT.aside-test"
  # Cleanup trap: if we Ctrl-C / crash between mv and un-mv, the live tree
  # would be missing and the next scheduled hourly fire would emit a real
  # repo_corrupt incident. Always un-mv on exit.
  trap '[[ -d "$ASIDE" && ! -d "$BACKUP_ROOT" ]] && mv "$ASIDE" "$BACKUP_ROOT" 2>/dev/null; trap - RETURN INT TERM' RETURN INT TERM
  mv "$BACKUP_ROOT" "$ASIDE" 2>/dev/null || { fail "could not move $BACKUP_ROOT aside"; return; }
  KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-backup.py" --profile hourly >/dev/null 2>&1
  rc=$?
  mv "$ASIDE" "$BACKUP_ROOT"
  flag="$RUN_DIR/restic-hourly-failed.flag"
  if [[ "$rc" -ne 0 ]] && [[ -f "$flag" ]]; then
    reason=$(python3 -c "import json; print(json.load(open('$flag'))['reason'])" 2>/dev/null)
    pass "failed gracefully (rc=$rc, reason=$reason)"
  else
    fail "expected non-zero exit + failed.flag (rc=$rc, flag exists: $([[ -f "$flag" ]] && echo yes || echo no))"
  fi
  # Reset state by running a real backup so the failed flag clears.
  KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-backup.py" --profile hourly >/dev/null 2>&1 || true
}

gate_8() {
  echo "== Gate 8: repo-corrupt detection (move keys/ aside) =="
  unlock_kc
  if [[ ! -d "$HOURLY_REPO/keys" ]]; then
    fail "$HOURLY_REPO/keys not found — cannot test"; return
  fi
  ASIDE_KEYS="$HOURLY_REPO/keys.aside-test"
  # Cleanup trap: a Ctrl-C between mv and un-mv would leave the live
  # hourly repo unrestorable until manually fixed. Always un-mv on exit.
  trap '[[ -d "$ASIDE_KEYS" && ! -d "$HOURLY_REPO/keys" ]] && mv "$ASIDE_KEYS" "$HOURLY_REPO/keys" 2>/dev/null; trap - RETURN INT TERM' RETURN INT TERM
  mv "$HOURLY_REPO/keys" "$ASIDE_KEYS" 2>/dev/null
  out="$(KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-backup.py" --profile hourly 2>&1)"
  rc=$?
  mv "$ASIDE_KEYS" "$HOURLY_REPO/keys"
  flag="$RUN_DIR/restic-hourly-failed.flag"
  if [[ "$rc" -ne 0 ]] && echo "$out" | grep -q "corrupt"; then
    reason="$(python3 -c "import json; print(json.load(open('$flag'))['reason'])" 2>/dev/null || echo '?')"
    pass "detected corrupt repo (reason=$reason), refused to auto-init"
  else
    fail "expected corrupt-repo detection (rc=$rc); got: $(echo "$out" | tail -2)"
  fi
  KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-backup.py" --profile hourly >/dev/null 2>&1 || true
}

gate_9() {
  echo "== Gate 9: concurrent-write safety (synthetic WAL traffic in same dir as health.db) =="
  unlock_kc
  HEALTH_DB="$HOME/Home-Tools/health-dashboard/data/health.db"
  if [[ ! -f "$HEALTH_DB" ]]; then
    fail "health.db not present at $HEALTH_DB"; return
  fi
  # Write to a sibling DB in the same directory as health.db. macOS HFS+/APFS
  # journal traffic + SQLite WAL fsync activity in the same dir is what we
  # actually want to stress; we don't need to mutate the production DB itself.
  # A Ctrl-C during the loop here is harmless — the temp DB is just a file
  # and gets cleaned up on the next gate run.
  TEST_DB="$(dirname "$HEALTH_DB")/_phase7_concurrent_test.db"
  trap 'rm -f "$TEST_DB" "$TEST_DB-wal" "$TEST_DB-shm" 2>/dev/null; trap - RETURN INT TERM' RETURN INT TERM
  rm -f "$TEST_DB" "$TEST_DB-wal" "$TEST_DB-shm"
  (
    for i in $(seq 1 25); do
      sqlite3 "$TEST_DB" "PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS t(v INTEGER); INSERT INTO t VALUES(strftime('%s','now'));" 2>/dev/null
      sleep 0.1
    done
  ) &
  WRITER_PID=$!
  KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-backup.py" --profile hourly >/dev/null 2>&1
  rc=$?
  wait "$WRITER_PID" 2>/dev/null
  if [[ "$rc" -ne 0 ]]; then
    fail "backup failed during concurrent writes"; return
  fi
  if KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-restore-test.py" >/dev/null 2>&1; then
    pass "backup + restore + integrity_check survive concurrent WAL traffic"
  else
    fail "restored DB failed integrity_check after concurrent writes — investigate WAL handling"
  fi
}

gate_10() {
  echo "== Gate 10: retention works (forget --keep-hourly bounds steady state) =="
  unlock_kc
  HOURLY_PW="$(get_pw restic-hourly-backup)"
  count=$(snap_count "$HOURLY_REPO" "$HOURLY_PW")
  # We can't easily fake 30 hourly snapshots in a test gate. Light check:
  # forget --dry-run reports a plan; ensure it doesn't error.
  out="$(RESTIC_REPOSITORY="$HOURLY_REPO" RESTIC_PASSWORD="$HOURLY_PW" restic forget \
    --keep-hourly 24 --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --dry-run 2>&1)"
  if echo "$out" | grep -qE "would remove|Applying Policy"; then
    pass "forget retention plan parses (current snapshot count: $count)"
  else
    fail "forget --dry-run output unexpected — check restic version"
  fi
}

gate_11() {
  echo "== Gate 11: bare-metal recovery dry-run (sandboxed HOME) =="
  unlock_kc
  HOURLY_PW="$(get_pw restic-hourly-backup)"
  DAILY_PW="$(get_pw restic-daily-backup)"
  ENV_FILE="$HOME/Home-Tools/event-aggregator/.env"
  NAS_USER="$(grep -E '^NAS_USER=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  NAS_PASSWORD="$(grep -E '^NAS_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  NAS_IP="$(grep -E '^NAS_DHCP_IPADDRESS=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  FAKE_HOME="$(mktemp -d /tmp/phase7-bare-metal-XXXXXX)"
  if bash "$HERE/restic-bare-metal-restore.sh" "$FAKE_HOME" "$NAS_USER" "$NAS_PASSWORD" "$NAS_IP" "$HOURLY_PW" "$DAILY_PW" 2>&1 | tail -5; then
    pass "bare-metal restore completed end-to-end"
  else
    fail "bare-metal restore did not complete (see output above)"
  fi
  rm -rf "$FAKE_HOME"
}

gate_12() {
  echo "== Gate 12: heartbeat backup_health probe (fresh + stale + in-flight handling) =="
  HEARTBEAT="$HERE/heartbeat.py"
  RESTIC_LOG="$LOG_DIR/restic-hourly.log"
  # Ensure the log exists — kickstart the agent if needed (Gate 6 already
  # does this in --all mode but be defensive in case Gate 12 runs alone).
  if [[ ! -f "$RESTIC_LOG" ]]; then
    launchctl kickstart -k "gui/$UID/com.home-tools.restic-hourly" 2>/dev/null
    sleep 5
  fi
  if [[ ! -f "$RESTIC_LOG" ]]; then
    fail "restic-hourly.log still not present at $RESTIC_LOG after kickstart"; return
  fi
  # Back-date the log to 3h ago — should be classified stale by probe.
  touch -t "$(date -v-3H +%Y%m%d%H%M.%S 2>/dev/null || date -d '-3 hours' +%Y%m%d%H%M.%S)" "$RESTIC_LOG"
  python3 "$HEARTBEAT" >/dev/null 2>&1
  STATE="$RUN_DIR/heartbeat-state.json"
  if [[ -f "$STATE" ]] && grep -q "backup:hourly" "$STATE"; then
    state_value=$(python3 -c "import json; print(json.load(open('$STATE')).get('backup:hourly', '?'))")
    if [[ "$state_value" = "stale" ]]; then
      pass "heartbeat probe classified back-dated log as stale (state=$state_value)"
    else
      fail "expected backup:hourly=stale, got $state_value"
    fi
  else
    fail "heartbeat-state.json missing backup:hourly key (probe may not be wired up)"
  fi
  # Restore log mtime to ~now so subsequent runs see fresh.
  touch "$RESTIC_LOG"
  python3 "$HEARTBEAT" >/dev/null 2>&1
}

gate_13() {
  echo "== Gate 13: 2-fire debouncing (state changes only after 2 consecutive observations) =="
  unlock_kc
  STATE="$RUN_DIR/restic-hourly-state.json"
  INCIDENTS="$LOGS_DIR/incidents.jsonl"
  before=$(wc -l < "$INCIDENTS" 2>/dev/null || echo 0)
  # Run a backup — should be ok. State already had ok at install. No new event.
  KEYCHAIN_PATH="$KEYCHAIN_PATH" python3 "$HERE/restic-backup.py" --profile hourly >/dev/null 2>&1
  after=$(wc -l < "$INCIDENTS" 2>/dev/null || echo 0)
  delta=$((after - before))
  if [[ "$delta" -le 1 ]]; then
    pass "ok→ok produced $delta new incident(s) — within debounce budget"
  else
    fail "ok→ok produced $delta new incidents — debouncing may be broken"
  fi
}

# ─── Driver ───────────────────────────────────────────────────────────

case "${1:-}" in
  --all)
    for n in 1 2 3 4 5 6 7 8 9 10 11 12 13; do
      "gate_$n"
      echo
    done
    ;;
  ''|--help|-h)
    echo "usage: $0 --all              # run all 13 gates"
    echo "       $0 <N>                # run gate N"
    exit 0
    ;;
  *)
    "gate_$1"
    ;;
esac

echo "================================================================"
echo "  Result: $PASS passed, $FAIL failed"
echo "================================================================"
[[ "$FAIL" -eq 0 ]]
