#!/usr/bin/env bash
# Mount the NAS Share1 at ~/Share1 on the mini.
# Run after every reboot until autofs is set up.
set -e
ENV_FILE=~/Home-Tools/event-aggregator/.env
[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found"; exit 1; }
NAS_USER=$(grep "^NAS_USER=" "$ENV_FILE" | cut -d= -f2-)
NAS_PASSWORD=$(grep "^NAS_PASSWORD=" "$ENV_FILE" | cut -d= -f2-)
NAS_IP=$(grep "^NAS_DHCP_IPADDRESS=" "$ENV_FILE" | cut -d= -f2-)
[ -n "$NAS_USER" ] && [ -n "$NAS_PASSWORD" ] && [ -n "$NAS_IP" ] || \
  { echo "ERROR: missing NAS_USER, NAS_PASSWORD, or NAS_DHCP_IPADDRESS in .env"; exit 1; }
NAS_PASSWORD_ENC=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=""))' "$NAS_PASSWORD")
mkdir -p ~/Share1
if mount | grep -q "/Users/homeserver/Share1"; then
  echo "Already mounted: $(mount | grep /Users/homeserver/Share1)"
  exit 0
fi
mount_smbfs "//${NAS_USER}:${NAS_PASSWORD_ENC}@${NAS_IP}/Share1" ~/Share1 2>&1 | \
  sed -e "s|${NAS_PASSWORD_ENC}|<REDACTED>|g" -e "s|${NAS_PASSWORD}|<REDACTED>|g"
unset NAS_PASSWORD NAS_PASSWORD_ENC
mount | grep "/Users/homeserver/Share1" && echo "MOUNT_OK"
