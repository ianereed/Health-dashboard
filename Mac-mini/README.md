# Mac mini Home Server

Setup and operations log for the headless Mac mini M4 home server that hosts
Ollama and the rest of the Home-Tools Python stack.

## Purpose

Private AI appliance living next to the router. Runs local LLM inference on
sensitive personal data (communications, finance, medical) without anything
leaving the house. Hosts scheduled Python jobs for the existing
`event-aggregator`, `meal-planner`, `health-dashboard`, and future
`finance-monitor` projects. Remote access from iPhone and laptop via
Tailscale.

## Hardware

- Apple Mac mini M4 base
- 24GB unified memory
- ~256GB SSD (base)
- Wired Ethernet to home router
- No attached display or keyboard after initial setup

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Physical setup (Ethernet, first power-on) | ✅ 2026-04-22 |
| 1 | First boot (account, hostname, pmset, sharing, firewall, auto-update) | ✅ 2026-04-22 |
| 2 | Remote access (Homebrew, Tailscale, Tailscale SSH from laptop) | ✅ 2026-04-22 |
| 3 | Core tools (`git`, `python@3.12`, `uv`, `gh`, `ollama`) | ✅ 2026-04-22 |
| 4 | Ollama configuration + model pulls | ✅ 2026-04-22 |
| 5 | Port `Home-Tools` repo to server | 🔄 Event-aggregator fully ported at `~/Home-Tools` and verified end-to-end (LaunchAgent fires, exits clean with status 0, daily digest delivered). Health-dashboard + meal-planner: not yet ported. |
| 6 | Minimal monitoring (launchd logs + Pushover) | ⏳ Pending |
| 7 | Backup (Time Machine + off-site) | ⏳ Pending |
| 8 | Finance automation scripts (YNAB, Amazon reconciliation) | ⏳ Pending |
| 9 | (Deferred) BlueBubbles iMessage bridge | ⏳ Deferred |
| 10 | (Deferred) Hermes Agent / OpenClaw eval | ⏳ Deferred |

## What's running right now

- **Hostname**: `homeserver.local` (Bonjour) / Tailscale `100.66.241.126`
- **Account**: `homeserver` (not `ianreed` — see path cleanup below)
- **Auto-login**: on
- **FileVault**: off (tradeoff: auto-recovery after reboots > at-rest
  encryption for this threat model)
- **Sleep**: disabled (`sleep 0`, `disksleep 0`, `displaysleep 0`); auto-restart
  after power failure enabled
- **Application Firewall**: on + Stealth Mode
- **Automatic OS security updates**: on
- **SSH**: Remote Login enabled; access via Tailscale SSH (identity-based,
  auth managed by Tailscale, not password)
- **Tailscale**: standalone Homebrew install running as a system daemon;
  `tailscale up --ssh` brings it online on boot
- **Ollama**: `brew services`, LaunchAgent at
  `~/Library/LaunchAgents/homebrew.mxcl.ollama.plist`, bound to
  `127.0.0.1:11434` only. Env vars baked into plist: `OLLAMA_FLASH_ATTENTION=1`,
  `OLLAMA_KV_CACHE_TYPE=q8_0`. Other env vars controlled per-request from
  Python (`keep_alive`, `options.num_ctx`).
- **Claude Code state** on the mini: full `~/.claude/` copied from laptop via
  rsync over Tailscale SSH (plans, memory, settings, slash commands). All 7
  memory project directories renamed from `-Users-ianreed-...` to
  `-Users-homeserver-...` so auto-memory resolves on the server.
- **Python environment pattern** (proven with event-aggregator):
  - `uv venv --python 3.12` in each project directory
  - `source .venv/bin/activate && uv pip install -r requirements.txt`
  - Run `install_scheduler.sh` from inside the activated venv — it auto-detects
    the venv's python3 via `which python3` and bakes that into the LaunchAgent
    plist
  - LaunchAgent logs: `/tmp/home-tools-<project>.log` (+ `-error.log`)
- **Models pulled**:
  - `qwen2.5:7b` (Q4_K_M, ~4.7GB) — event-aggregator extraction model
  - `qwen2.5vl:7b` (~6GB) — event-aggregator vision/image pipeline
  - `qwen2.5:14b` (Q4_K_M, ~9GB) — workhorse for future finance-monitor work
  - `llama3.2:3b` (Q4_K_M, ~2GB) — fast path for simple classification
  - `nomic-embed-text` (F16, ~275MB) — embeddings for future RAG

## Key decisions (2026-04-22)

- **Server account name**: `homeserver` (not `ianreed`). Trades off ~20
  hardcoded path references across 6 files in the repo for cleaner mental
  separation and nicer SSH syntax. See
  `.claude/projects/.../project_mac_mini_path_cleanup.md` for the one-shot
  `sed` fix command to run after cloning to the server.
- **FileVault off** over auto-recovery: threat model is home-network only,
  behind a locked door, with no physical targeting expected. Auto-login
  lets launchd services come back up unattended after reboots/power events.
- **Minimal monitoring**: launchd log files + Pushover/ntfy for failure
  pings. No dashboards, no Uptime Kuma, no iStatistica. Add later if
  actually needed.
- **Accept Homebrew's opinionated Ollama plist**: Only 2 of 7 env vars
  survive brew's plist regeneration. Acceptable because the two that stick
  (FLASH_ATTENTION, KV_CACHE_TYPE) are the memory-critical ones. The rest
  (context length, keep-alive) are better controlled per-request from
  Python anyway.
- **No Apple ID / iCloud** on the server: not needed for any current workload.
  Will revisit only if the BlueBubbles iMessage bridge is actually deployed.
- **No Apple Intelligence**: wrong tool for a headless server, competes with
  Ollama for unified memory, requires Apple ID we aren't signing into.
- **Code lives at `~/Home-Tools`, NOT `~/Documents/GitHub/Home-Tools`** (found
  2026-04-22). macOS TCC protects `~/Documents`, `~/Downloads`, `~/Desktop`,
  `~/Pictures`, `~/Music`, `~/Movies`. launchd agents don't have Full Disk
  Access by default, so Python invoked by a LaunchAgent hangs indefinitely on
  `getpath_readlines` → `__open_nocancel` when the venv lives under
  `~/Documents`. Running the same script from an SSH shell works (different
  TCC context), which makes the bug deceptively sneaky. Rule: **on this
  server, all project code lives at `~/<project-name>/` or `~/src/`, never
  under the protected user folders.**

## Critical file paths

| Path | Purpose |
|---|---|
| `~/Home-Tools` | The main repo on the mini (outside TCC-protected folders) |
| `~/Home-Tools/event-aggregator/.venv` | Per-project Python venv |
| `~/Library/LaunchAgents/homebrew.mxcl.ollama.plist` | Ollama service definition |
| `~/Library/LaunchAgents/com.home-tools.*.plist` | Home-tools LaunchAgents |
| `/opt/homebrew/var/log/ollama.log` | Ollama stdout+stderr |
| `/tmp/home-tools-<project>.log` | Per-project LaunchAgent stdout+stderr |

## Verification commands

Run these at any point to confirm the server is healthy:

```bash
# Event-aggregator last run completed cleanly (PID `-`, exit status `0`)
launchctl list | grep event-aggregator

# Ollama is up, bound to loopback only
sudo lsof -iTCP:11434 -sTCP:LISTEN -n -P

# Hot-path inference works
time ollama run qwen2.5:14b "say only: ready"

# All models are present
ollama list

# Power policy is correct
sudo pmset -g | grep -E '^ (sleep|disksleep|displaysleep|womp|autorestart)'

# Tailscale is connected
tailscale status

# No unexpected listeners
sudo lsof -iTCP -sTCP:LISTEN -n -P

# Automatic updates on
softwareupdate --schedule
```

## Related documents

- **`Mac-mini/PLAN.md`** — living working plan. Read this first when
  resuming a session. Has the next concrete action + per-phase detailed
  steps + known gotchas.
- `Mac-mini/original-context.rtf` — the full planning conversation that led
  to the purchase decision (Apr 19–21)
- `~/.claude/plans/i-want-you-to-tranquil-pearl.md` — frozen initial setup
  plan (phases 0–7 as originally scoped). Preserved for history; superseded
  by `PLAN.md`.

## Update discipline

Keep this README current as phases complete. Entry points for updates:

- Add a row to the status table (or flip an emoji) when a phase finishes
- Add to the "What's running" section when a new long-running service comes
  up (Pushover, BlueBubbles, a new LaunchAgent)
- Record any new decision + its reasoning in the "Key decisions" section
- Don't put command output here — put it in the plan file or a separate log
