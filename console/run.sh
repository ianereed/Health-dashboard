#!/bin/bash
# Wrapper for the Mini Ops console LaunchAgent.
# Reuses the jobs/ venv since console depends on streamlit + jobs imports.
set -euo pipefail

# launchd's environment is sparse — /sbin is needed for ifconfig on macOS.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin"

cd "$(dirname "$0")/.."   # ~/Home-Tools

VENV="$(pwd)/console/.venv"
if [ ! -d "$VENV" ]; then
    /opt/homebrew/bin/python3.12 -m venv "$VENV"
    "$VENV/bin/pip" install -q streamlit requests
    # Console imports jobs.huey, so install jobs reqs into the same venv
    "$VENV/bin/pip" install -q -r jobs/requirements.txt
fi
source "$VENV/bin/activate"

KEYCHAIN_PATH="${KEYCHAIN_PATH:-$HOME/Library/Keychains/login.keychain-db}"
security unlock-keychain -p "" "$KEYCHAIN_PATH" 2>/dev/null || true
export HOME_TOOLS_HTTP_TOKEN="$(security find-generic-password -a 'home-tools' -s 'jobs_http_token' -w "$KEYCHAIN_PATH" 2>/dev/null || echo '')"

# Tailscale IP (so we don't expose console on en0/lo0). Don't let a missing
# ifconfig kill the script — fall back to localhost.
set +e
TAILSCALE_IP="$(ifconfig 2>/dev/null | awk '/inet 100\./ {print $2; exit}')"
set -e
TAILSCALE_IP="${TAILSCALE_IP:-127.0.0.1}"

# jobs-http binds to the Tailscale IP; MagicDNS self-resolution doesn't work
# on macOS, so point the jobs client directly at the detected IP.
export HOME_TOOLS_HTTP_URL="http://${TAILSCALE_IP}:8504"

exec "$VENV/bin/streamlit" run console/app.py \
    --server.port 8503 \
    --server.address "$TAILSCALE_IP" \
    --server.headless true \
    --browser.gatherUsageStats false
