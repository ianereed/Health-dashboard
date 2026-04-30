#!/usr/bin/env bash
# Install nas-intake on the mini: venv + LaunchAgent.
# Run from the mini, in the project root, after `git pull`.
# Idempotent — safe to re-run after pulling updates.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.home-tools.nas-intake"
PLIST_SRC="${PROJECT_ROOT}/${LABEL}.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

cd "$PROJECT_ROOT"

# 1. venv
if [ ! -d ".venv" ]; then
  echo "==> creating venv"
  uv venv --python 3.12
fi

# 2. deps (none right now; harmless to run)
echo "==> installing deps (if any)"
source .venv/bin/activate
uv pip install -r requirements.txt 2>&1 | grep -v "Audited 0 packages" || true

# 3. copy plist
echo "==> installing LaunchAgent at ${PLIST_DST}"
mkdir -p "$(dirname "$PLIST_DST")"
cp "$PLIST_SRC" "$PLIST_DST"
chmod 644 "$PLIST_DST"

# 4. (re)load
if launchctl list | awk '{print $3}' | grep -qx "$LABEL"; then
  echo "==> kickstarting (already loaded)"
  launchctl kickstart -k "gui/$(id -u)/${LABEL}" || true
else
  echo "==> loading"
  launchctl load "$PLIST_DST"
fi

# 5. show status
echo
launchctl list | grep "$LABEL" || echo "WARN: $LABEL not in launchctl list"
echo
echo "==> install OK. Watch log: tail -f /Users/homeserver/Library/Logs/home-tools-nas-intake.log"
