# Event Aggregator

Monitors your messaging sources for mentions of upcoming events and writes them to Google Calendar.
Also extracts action items and writes them to Todoist. Runs locally on your Mac every 15 minutes
via launchd. All LLM extraction happens through a local Ollama process — your message content
never leaves your machine.

---

## Status: All phases complete

| Phase | What | Status |
|-------|------|--------|
| 1 | Scaffold + mock pipeline | ✅ Done |
| 2 | Gmail + Google Calendar writer | ✅ Done |
| 3 | iMessage + WhatsApp (local SQLite) | ✅ Done |
| 4 | Slack + Discord | ✅ Done |
| 5 | Messenger + Instagram (Notification Center) | ✅ Done |
| 6 | GCal reader + year-ahead analysis + digests | ✅ Done |
| 7 | launchd scheduler | ✅ Done |
| 8 | Smarts upgrade (confidence banding, update/cancel detection) | ✅ Done |
| 9 | Todoist todo extraction | ✅ Done |

---

## Quick start

```bash
cd event-aggregator
pip install -r requirements.txt
# Ollama must be running: ollama serve

# Safe test — no API writes, no Slack posts:
python main.py --mock --dry-run

# Pure unit tests (no Ollama, no APIs):
python -m pytest tests/ -v
```

---

## Architecture

```
Sources            Connectors         Extractor            Dedup          Output
────────────────────────────────────────────────────────────────────────────────
Gmail              gmail.py    ─┐
GCal invites       gcal.py     ─┤                        Fingerprint ──→ GCal write
Slack              slack.py    ─┤──→ RawMessage ──→ ──→ + fuzzy      ──→ Todoist task
iMessage           imessage.py ─┤    list        Ollama   title match ──→ Slack thread
WhatsApp           whatsapp.py ─┤                (local)              ──→ event log
Discord            discord.py  ─┤
Messenger/IG       notifs.py   ─┘
```

**Privacy invariant**: `body_text` goes only to local Ollama. Never logged, never printed,
never shown to Claude. Use `--mock --dry-run` for all demos/debugging.

---

## Extraction smarts

One Ollama call per message extracts both events and todos simultaneously:

- **Source-aware prompts** — different templates for email / chat / calendar with context enrichment (sender, subject, channel, attendees)
- **User timezone** (`America/Los_Angeles`) injected; GCal events store correct local time
- **Banded confidence** — below medium = skip, medium–high = `[?]` prefix on title, high+ = normal
- **Update detection** — Ollama signals reschedule → fuzzy lookup → patches existing GCal event
- **Cancellation detection** — Ollama signals cancel → fuzzy lookup → deletes GCal event
- **Cross-calendar dedup** — checks calendar snapshot before writing (catches events already on other calendars)
- **Conflict detection** — warns if another event is within ±30 min of a write
- **Category color coding** — GCal event color set by category (work/personal/social/health/travel/other)

---

## Calendar intelligence (Phase 6)

Beyond writing events, the pipeline also:
- **Scans the full year ahead** for scheduling conflicts and travel-time risks
- **Daily digest** (next 14 days): new/changed events + grouped conflict warnings → posted to `ian-event-aggregator` Slack thread
- **Weekly digest** (14 days → 1 year): same format for far-out events
- **Batched run notifications**: all event actions from a run posted as one Slack message in the day thread
- **Local log**: `event_log.jsonl` (gitignored) — every create/update as a JSONL record

All Slack output goes to `#ian-event-aggregator` channel with daily threading (one thread per day,
all actions as replies).

---

## Todo extraction (Phase 9)

In addition to calendar events, the extractor also pulls out action items:
- Commitments, assigned tasks, and follow-ups extracted from the same messages
- Written to the "automated todo aggregation" Todoist project
- Deduped via fingerprint (same todo from same message is never created twice)
- Priority, due date, and source context included in the Todoist task description
- Silently disabled if `TODOIST_API_TOKEN` is absent from `.env`

---

## Setup checklist

Before each phase, add the corresponding `.env` variables from `.env.example`.

### macOS permissions required
- **Full Disk Access** → System Settings → Privacy & Security → Full Disk Access → add `Python.app`
  (needed for iMessage, WhatsApp, and Notification Center connectors)

### Credentials directory
`event-aggregator/credentials/` is gitignored. It will hold:
- `gmail_oauth.json` — OAuth2 client secrets from Google Cloud Console
- `gmail_token.json` — auto-generated after first OAuth flow
- `gcal_token.json` — auto-generated after first OAuth flow

### Install scheduler (Phase 7)
1. Run `bash install_scheduler.sh`
2. Logs: `/tmp/home-tools-event-aggregator.log` (stdout), `/tmp/home-tools-event-aggregator-error.log` (stderr)
3. To uninstall: `launchctl unload ~/Library/LaunchAgents/com.home-tools.event-aggregator.plist && rm ~/Library/LaunchAgents/com.home-tools.event-aggregator.plist`

---

## Key files

| File | Purpose |
|------|---------|
| `main.py` | CLI entry point — `--mock`, `--dry-run`, `--source` |
| `models.py` | `RawMessage`, `CandidateEvent`, `CandidateTodo`, `WrittenEvent` dataclasses |
| `extractor.py` | Ollama LLM extraction + output validation (returns events + todos) |
| `dedup.py` | Fingerprint + fuzzy dedup logic for both events and todos |
| `state.py` | JSON state (last_run, seen IDs, fingerprints, todoist project ID) — auto-pruned |
| `config.py` | `.env` loading + per-source validation |
| `connectors/base.py` | `BaseConnector` abstract class |
| `writers/google_calendar.py` | GCal create/update/delete + conflict check |
| `writers/todoist_writer.py` | Todoist REST API — get/create project + create task |
| `analyzers/calendar_analyzer.py` | Year-ahead scan, conflict + location analysis |
| `notifiers/slack_notifier.py` | Channel thread posting — batched events, todos, run summary, digests |
| `notifiers/digest.py` | Daily/weekly digest builder |
| `logs/event_log.py` | JSONL audit log |
| `tests/mock_data.py` | **Only** source of test data — all synthetic |
| `state.json` | Runtime state — gitignored, created on first run |
| `event_log.jsonl` | Audit log — gitignored, created on first run |

---

## Development rules

1. **Always use `--mock --dry-run` when working with Claude** — `--mock` alone writes synthetic events
   to real GCal; `--dry-run` is required to suppress all writes
2. Real message content must never appear in conversation output or logs
3. Share only tracebacks and event counts, never message text
4. `body_text` is never printed — log only `source` and `id`
5. `state.json`, `event_log.jsonl`, OAuth tokens, and `credentials/` are all gitignored
