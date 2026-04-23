# Mac mini Home Server — Working Plan

Living plan for the ongoing build. Update as phases advance. Pair this with
`Mac-mini/README.md` (the state-of-the-project page) and the
`.claude/projects/.../memory/` entries (the accumulated lessons).

---

## Quick status (as of 2026-04-22)

Phases 0–5 complete. Event-aggregator + health-dashboard both running on the
mini under launchd at `~/Home-Tools/<project>` with `.venv`-based LaunchAgents.
iPhone Health Auto Export now posts to `http://homeserver:8095/` over
Tailscale. Meal-planner stays on the laptop (Apps Script, nothing to run on
the mini). Phases 6, 7, 8 remain.

See `README.md` for the full status table and running services.

---

## Resume from here

**Next single action**: Phase 6 — minimal failure monitoring. Pushover (or
ntfy) + a shared `notify.sh` that each LaunchAgent calls on non-zero exit.
Detailed steps in Phase 6 below.

Before touching anything, run these to confirm the server is still healthy:

```bash
ssh homeserver@homeserver '
  tailscale status | head -3
  launchctl list | grep -E "ollama|event-aggregator|health-dashboard"
  sudo lsof -iTCP:11434 -sTCP:LISTEN -n -P
  sudo lsof -iTCP:8095 -sTCP:LISTEN -n -P
'
```

Expected: tailscale connected, Ollama + event-aggregator + 4 health-dashboard
LaunchAgents registered with clean exit status, Ollama on `127.0.0.1:11434`,
receiver on `*:8095`.

---

## Phase 5b — Port health-dashboard (DONE 2026-04-22)

Health-dashboard is live on the mini. Receiver on port 8095, collect at
7:00/7:20, intervals-poll every 5 min, staleness at 7am/9pm. iPhone posts
to `http://homeserver:8095/` over Tailscale. Laptop plists renamed to
`*.plist.disabled` so they don't auto-load. Records kept below for future
reference / if we ever port a similar project.

### Gotchas encountered during the port

- **Login keychain not reachable from LaunchAgents.** `homeserver`'s aqua
  session on this headless mini never got the interactive login that
  auto-unlocks the default keychain. Symptoms: `keyring.get_password`
  returns `errSecAuthFailed` (security CLI exit 152) from within a
  LaunchAgent, even though it works from an SSH shell and even though the
  keychain *is* in the search list. Fix: recreate `login.keychain-db` with
  empty password (`security create-keychain -p ""`), set no-auto-lock, and
  have the shim in `collectors/__init__.py` explicitly unlock it on import.
- **keyring>=25 ignores `Keyring.keychain`.** Even after fixing unlock,
  `keyring` can't be pointed at a specific keychain any more (upstream
  issue #623). The shim works around this by monkey-patching
  `keyring.get_password` to shell out to `security` with `KEYCHAIN_PATH`.
- **Keychain migration needed explicit target.** `security add-generic-password`
  from SSH writes to `System.keychain` (root-only → "Write permissions
  error") unless you pass the target keychain as the final positional arg.
  The same is true on the mini; the default-keychain `-d user` setting
  exists in the user preference domain but doesn't propagate to the
  Security framework calls from ssh.

### Why it wasn't trivial

- Health-dashboard ships **4 plists** (collect, intervals-poll, receiver,
  staleness), not 1. All must install cleanly.
- May have its own `requirements.txt` + credential files; treat it like a
  fresh project, not a quick re-run of event-aggregator.

### Steps (execute on the mini via SSH)

1. **Sanity-read the existing memory and code**:
   ```bash
   ssh homeserver@homeserver '
     ls ~/Home-Tools/health-dashboard/
     cat ~/Home-Tools/health-dashboard/README.md 2>/dev/null || true
     ls ~/Home-Tools/health-dashboard/config/
   '
   ```
   Read `project_health_dashboard.md` memory before proceeding.

2. **Path-cleanup check** (plists were part of the earlier sed sweep, but
   verify nothing in health-dashboard still references the wrong paths):
   ```bash
   grep -r '/Users/homeserver/Documents/GitHub' ~/Home-Tools/health-dashboard 2>/dev/null
   grep -r '/Users/ianreed' ~/Home-Tools/health-dashboard 2>/dev/null
   # Both should return nothing.
   ```

3. **Clear any stale bytecode** (the earlier sed corrupted `.pyc` files —
   this will have done the same to health-dashboard):
   ```bash
   find ~/Home-Tools/health-dashboard -type d -name __pycache__ -exec rm -rf {} +
   ```

4. **Build the venv**:
   ```bash
   cd ~/Home-Tools/health-dashboard
   uv venv --python 3.12
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```

5. **Migrate credentials / .env from laptop** (same scp pattern as
   event-aggregator, only what's needed):
   ```bash
   # FROM laptop:
   cd ~/Documents/GitHub/Home-Tools/health-dashboard
   ls .env credentials/ 2>/dev/null   # see what exists
   scp .env homeserver@homeserver:~/Home-Tools/health-dashboard/
   scp -r credentials homeserver@homeserver:~/Home-Tools/health-dashboard/ 2>/dev/null || true
   # Back on mini:
   ssh homeserver@homeserver 'cd ~/Home-Tools/health-dashboard && chmod 600 .env credentials/*.json 2>/dev/null'
   ```

6. **Smoke-test on the mini via SSH shell** (not launchd):
   ```bash
   cd ~/Home-Tools/health-dashboard
   source .venv/bin/activate
   python -c "import main" || python -m py_compile *.py  # adapt to actual entrypoint
   # Run whatever equivalent of --mock/--dry-run exists (may differ from event-aggregator).
   ```
   If there's no mock mode, skip the smoke test and trust the LaunchAgent
   install step.

7. **Apply the outstanding fixes** noted in `project_health_dashboard.md`
   memory (3 remaining steps). Resolve those before loading any plist —
   they're the reason this project hasn't been running already.

8. **Install the LaunchAgents** (4 of them). Health-dashboard may or may not
   ship an `install_scheduler.sh`. If it does, activate the venv first and
   run it. If not, copy the plist files to `~/Library/LaunchAgents/` and
   `launchctl load` each one, rewriting the Python path to
   `<project>/.venv/bin/python3`.

9. **Verify**:
   ```bash
   launchctl list | grep health-dashboard
   ls -la /tmp/home-tools-health-dashboard*.log
   ```
   PID `-` + exit status `0` + nonzero log sizes after first fire = success.

### Known gotchas to watch for

- **Empty log + Python `S` state for minutes** → TCC hang. Move whatever
  path is blocked out of `~/Documents`, `~/Downloads`, `~/Desktop`, etc.
  (Shouldn't happen since we're already at `~/Home-Tools`, but stay alert
  for any code that writes to `~/Documents/whatever`.)
- **`bad marshal data` on import** → stale `.pyc` from the earlier sed pass.
  `find ... -name __pycache__ -exec rm -rf {} +`.
- **`launchctl list` shows non-zero exit status** → always read the error
  log first. It may be Python logging at INFO (stderr by default) — cosmetic
  — or actual traceback.

### Skip meal-planner

Meal-planner is Google Apps Script + Gemini cloud. Nothing to run on the
mini. Drop from Phase 5 scope; the laptop will continue to deploy Apps
Script updates.

---

## Phase 6 — Minimal monitoring

Goal: get a phone ping when any LaunchAgent fails, without building
dashboards.

1. **Sign up for Pushover** (https://pushover.net, $5 one-time per device)
   OR self-host ntfy. Pushover is faster to set up.
2. **Store Pushover tokens in macOS Keychain** (not in plaintext `.env`):
   ```python
   # On the mini, one-time in a Python shell:
   import keyring
   keyring.set_password("pushover", "app_token", "xxx")
   keyring.set_password("pushover", "user_key", "xxx")
   ```
3. **Write a shared `~/Home-Tools/bin/notify.sh`** that reads the Keychain
   via the `security` CLI and POSTs to Pushover. Wrap each LaunchAgent's
   Python invocation with a shell that traps non-zero exits and calls
   `notify.sh`.
4. **Weekly SSH-failure digest** as a LaunchAgent:
   `log show --predicate 'process == "sshd"' --last 7d | grep -i "failed\|invalid"`
   → pipe to notify.sh once a week.
5. **Monthly port audit** — not automated; set a calendar reminder to run
   `sudo lsof -iTCP -sTCP:LISTEN -n -P` and compare to the expected
   baseline (sshd, screensharing, ollama, utun*). Anything else = investigate.

### What to skip unless actually needed

- iStatistica / Stats menu bar apps (can't see them, it's headless)
- Uptime Kuma / Netdata dashboards
- Structured log shipping

---

## Phase 7 — Backup

Goal: 3-2-1 backup for the mini so we can recover from disk failure or
ransomware.

1. **Local snapshots — Time Machine** to an external SSD or SMB share on a
   NAS:
   - System Settings → General → Time Machine → Add Backup Disk
   - Check "Encrypt backups" (critical)
   - Leave on automatic hourly schedule
2. **Off-site — restic or Arq** to B2 / Wasabi / S3. Restic is free, Arq is
   $50/yr with a nicer GUI. Either works.
   - Key goes in 1Password (not on the mini — defeats the purpose)
   - Initial backup may take hours; let it run overnight
   - Daily incremental after that
3. **Test a restore.** Pick one file, restore it to a scratch dir, diff.
   Untested backups aren't backups.
4. **Exclude** from both: `.venv/` directories, `__pycache__/`, `.git/`
   (optional, git lives on GitHub anyway), large model weights (they're
   redownloadable via `ollama pull`).

---

## Phase 8 — Finance automation (the big new work)

This is the original driver for the server. Multi-week scope. Work at
`~/Home-Tools/finance-monitor/` (new directory, not yet created).

### Planned sub-phases

1. **YNAB read-only client** — Python package wrapping YNAB's REST API with
   delta polling + local SQLite cache. No Ollama yet.
2. **Amazon order reconciliation** — Gmail API parses Amazon confirmation
   emails, matches them to YNAB Amazon transactions, Ollama categorizes item
   lists, writes subtransactions via YNAB PATCH.
3. **Daily morning digest** — cron (launchd), Ollama summarizes yesterday's
   spending, sends via Pushover / iMessage (once BlueBubbles is up).
4. **Weekly review + monthly retirement checks** — on top of the daily.
5. **Anomaly detection** — flag unusual payees, large charges, missed
   deposits.

### Security controls (per the original research)

- YNAB token in macOS Keychain, never in `.env`.
- Trusted-tier / untrusted-tier split: email parsing (untrusted input) can
  only *propose* categorizations; never POST to YNAB automatically above a
  threshold. User approves via iMessage for anything >$200 or new payee.
- Gmail OAuth in read-only scope (no send access).
- Per-request `keep_alive=-1` + `num_ctx=8192` to Ollama for batch email
  parses; otherwise defaults.

This phase deserves its own PLAN.md when we get to it — don't try to fit it
all in here.

---

## Phase 9–10 — Deferred

- **BlueBubbles iMessage bridge** — requires signing into iCloud on the
  mini. Defer until we actually want iMessage-based control of the finance
  monitor.
- **Hermes Agent / OpenClaw evaluation** — original research treated these
  as existing; I was unable to verify OpenClaw at all in 2026 web searches
  (likely prior-context hallucination). Before installing either, do a
  real-world verification pass. Finance automation works fine without an
  agent framework; this is optional polish.

---

## Reference

- `Mac-mini/README.md` — current state, running services, key decisions
- `Mac-mini/original-context.rtf` — original planning conversation (Apr 19–21)
- `~/.claude/plans/i-want-you-to-tranquil-pearl.md` — frozen initial setup
  plan (phases 0–7 as originally scoped); preserved for history
- Memory entries to pull context from at session start:
  - `project_mac_mini_path_cleanup.md` — two sed rewrites + pycache gotcha
  - `feedback_macos_tcc_avoid_protected_paths.md` — why code lives at
    `~/Home-Tools`, not `~/Documents`
  - `feedback_mac_mini_readme_upkeep.md` — keep README in sync
  - `project_health_dashboard.md` — pre-existing outstanding fixes
  - `project_event_aggregator.md` / `project_setup_state.md` — what the
    event-aggregator expects
  - `feedback_privacy.md` + `feedback_mock_dryrun.md` — never run real data
    through Claude; always `--mock --dry-run`

---

## How to pick up next session

Paste into the opening prompt something like:

> Read `Mac-mini/PLAN.md` and `Mac-mini/README.md` in this repo, then let's
> continue the Mac mini build from where we left off. Next up is Phase 5b
> (port health-dashboard).

That's enough context — the plan points at the memory files and the README,
so Claude will pick up from there.
