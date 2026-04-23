# Apple Health Auto Export — Automation Setup

## How It Works

Health Auto Export sends HTTP POST requests with JSON data to the receiver
running on the Mac mini (`http://homeserver:8095/` via Tailscale MagicDNS).
The server parses the data and writes it directly to the dashboard's SQLite
database.

## Important iOS Limitation

**iOS does NOT allow apps to run in the background at a specific time.**

The app cannot guarantee exports at exact times. Actual execution depends on:
- Device being **unlocked**
- **Background App Refresh** enabled (Settings > General > Background App Refresh)
- **Not** in Low Power Mode
- iOS deciding when to allocate background resources

## Recommended Setup for Reliable Automation

### Best approach: Widget + Charging routine

1. **Add the Health Auto Export widget** to your iPhone home screen
2. Tap it once when you plug in your phone at night or in the morning
3. This triggers an immediate manual export — most reliable method

### Background automation (best effort)

The app will also try to export in the background, but iOS controls when this happens.
To maximize background reliability:
- Keep **Background App Refresh** ON for Health Auto Export
- Keep the app **not force-closed** (don't swipe it away in app switcher)
- Disable **Low Power Mode** or add Health Auto Export to exceptions
- The app syncs more reliably when the phone is **charging and on WiFi**

### Shortcuts integration (alternative)

You can create an iOS Shortcut automation that triggers Health Auto Export:
1. Open Shortcuts > Automation > + > **When Charger Is Connected**
2. Add action: Health Auto Export > Export
3. Toggle "Run Immediately" ON

This gives you automatic exports every time you plug in your phone.

## Current App Configuration

In Health Auto Export:
- **Automation type**: REST API
- **URL**: `http://homeserver:8095/` (Tailscale MagicDNS — works from any
  network, survives router restarts). Fallback: Tailscale IP
  `http://100.66.241.126:8095/`, or `http://homeserver.local:8095/` on the
  home LAN.
- **Format**: JSON (Version 2)
- **Metrics selected**: Heart Rate, Resting Heart Rate, Sleep Analysis, Heart Rate Variability
- **Sync cadence**: Every 6 hours (background, best effort)

## If the URL stops working

Tailscale MagicDNS is the primary path, so local IP changes don't matter.
If exports suddenly stop:
1. Open Tailscale on the iPhone — is it connected? Any "needs attention"?
2. From the Mac mini: `curl -sS http://127.0.0.1:8095/` — should return
   "Health Auto Export receiver is running."
3. Check `launchctl list | grep health-dashboard.receiver` on the mini —
   PID present, last exit 0.

## Verifying It Works

On the Mac mini:
```
tail -f ~/Library/Logs/health-dashboard/receiver.log
```

You should see lines like:
```
Received: 7 HR samples, 1 sleep records
```
