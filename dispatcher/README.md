# dispatcher — Home-Tools Slack router

Long-running Socket Mode bot that routes incoming Slack messages/uploads to
the correct Home-Tools project. Sits between Slack and
`event-aggregator` / `finance-monitor` / NAS staging.

## What it does

- **`#ian-image-intake`** — user drops an image or PDF. Dispatcher downloads
  it, classifies locally (qwen2.5vl:7b via Ollama; no cloud), and routes:
  - `Financial` → `finance-monitor/intake/` (finance-monitor watcher picks up)
  - `Events` → `event-aggregator/main.py ingest-image` (proposal posted in
    `#ian-event-aggregator`)
  - Healthcare / Documents / Recipes / others → `nas-staging/<category>/<year>/`
    on the mini (ready to flush to the NAS once mounted)
  - Confidence <0.3 → `nas-staging/Unsorted/`; user can reply `!route <cat>`
    in the same thread to fix
- **`#ian-event-aggregator`** — interactive commands that shell out to
  event-aggregator's CLI: `approve`, `reject`, `add: …`, `status`, `pending`,
  `what's on <timeframe>`, `conflicts …`, `help`

## Local-only model policy

All classification, OCR, and structured extraction runs on the mini's Ollama.
The dispatcher **does not** call Gemini, OpenAI, Anthropic, or any other
cloud model. This is enforced by:

- Using event-aggregator's `_analyze_local` path only (the cloud fallback is
  deleted from event-aggregator in the same rollout).
- No API keys for cloud models in `.env.example`.

## Setup (on the mini)

1. Create the Slack app "Home Router Bot" at <https://api.slack.com/apps>.
   Enable Socket Mode; create an App-Level Token with `connections:write`
   (`xapp-…`) and a Bot Token with scopes:
   `channels:history, channels:read, groups:history, groups:read, chat:write,
   files:read, reactions:write`.
2. Install the app; invite the bot to `#ian-event-aggregator` and
   `#ian-image-intake`.
3. Stash tokens in the login keychain:
   ```bash
   security add-generic-password -U -s dispatcher-slack -a app_token \
     -w "xapp-..." ~/Library/Keychains/login.keychain-db
   security add-generic-password -U -s dispatcher-slack -a bot_token \
     -w "xoxb-..." ~/Library/Keychains/login.keychain-db
   ```
4. `cp .env.example .env` and set `ALLOWED_SLACK_USER_IDS`.
5. `bash install.sh` — creates venv, copies plist, loads LaunchAgent,
   runs `main.py check`.

## Local dev (laptop)

Use `.env` tokens instead of keychain. Override the paths:

```
EVENT_AGGREGATOR_DIR=/Users/ianreed/Documents/GitHub/Home-Tools/event-aggregator
EVENT_AGGREGATOR_PYTHON=/Users/ianreed/Documents/GitHub/Home-Tools/event-aggregator/.venv/bin/python3
FINANCE_MONITOR_INTAKE=/Users/ianreed/Documents/GitHub/Home-Tools/finance-monitor/intake
```

Then `python main.py serve` — it'll connect to Slack over Socket Mode and
start receiving events.

## Files

- `main.py` — CLI entry (`serve`, `check`)
- `slack_bot.py` — Socket Mode event handlers
- `router.py` — category → destination mapping + file moves
- `classifier.py` — subprocess wrapper around event-aggregator's local vision
- `commands.py` — interactive command parser + CLI shell-out
- `config.py` — env / keychain token resolution
- `com.home-tools.dispatcher.plist` — KeepAlive LaunchAgent
- `install.sh` — installer for the mini
- `tmp/` — transient download buffer
- `nas-staging/` — local staging tree (flushed to NAS later)
