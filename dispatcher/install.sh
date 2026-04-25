#!/usr/bin/env bash
# Install the dispatcher LaunchAgent on the mini.
# Run on the mini after: git pull, then fill in keychain entries (see below).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$HERE/com.home-tools.dispatcher.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.home-tools.dispatcher.plist"

echo "== dispatcher install =="
echo "  project: $HERE"

if [[ ! -d "$HERE/.venv" ]]; then
  echo "  creating venv (.venv) with Python 3.12"
  cd "$HERE"
  uv venv --python 3.12 || python3.12 -m venv .venv
fi

echo "  installing requirements"
"$HERE/.venv/bin/pip" install -q -r "$HERE/requirements.txt"

# Sanity-check keychain entries (non-fatal — let `main.py check` report)
echo "  verifying keychain entries (dispatcher-slack/app_token, bot_token)"
for acct in app_token bot_token; do
  if ! security find-generic-password -s dispatcher-slack -a "$acct" \
      "$HOME/Library/Keychains/login.keychain-db" >/dev/null 2>&1; then
    echo "    MISSING: security add-generic-password -U -s dispatcher-slack -a $acct -w \"<token>\" \\"
    echo "               $HOME/Library/Keychains/login.keychain-db"
  fi
done

echo "  copying plist to $PLIST_DST"
mkdir -p "$(dirname "$PLIST_DST")"
cp "$PLIST_SRC" "$PLIST_DST"

if launchctl list | grep -q com.home-tools.dispatcher; then
  echo "  unloading previous LaunchAgent"
  launchctl unload "$PLIST_DST" || true
fi

echo "  loading LaunchAgent"
launchctl load "$PLIST_DST"

echo
echo "Running config/CLI check:"
"$HERE/.venv/bin/python3" "$HERE/main.py" check || true

echo
echo "Done. Tail the log with:"
echo "  tail -f /tmp/home-tools-dispatcher.log"
