# nas-intake

Watcher that processes documents dropped into NAS `intake/` folders, files
them under their parent (`<parent>/<year>/<doc-type>/<date>_<slug>/`), and
appends a per-parent journal entry. Runs every 5 min as a LaunchAgent on
the Mac mini home server.

## Usage

Drop a PDF or image into any `intake/` subfolder under `~/Share1/` on the
mini (e.g. `~/Share1/Healthcare/0-Ian Healthcare/intake/labs.pdf`).
Within ~10 minutes (two ticks of the watcher: first records, second
processes), the file is:

1. OCR'd + classified locally via event-aggregator's pipeline (qwen2.5vl + qwen3).
2. Filed at `~/Share1/Healthcare/0-Ian Healthcare/<year>/<doc-type>/<date>_<slug>/`
   with the original PDF + page renderings + extraction.txt + extraction.pdf
   + summary.txt.
3. Source moved to `<intake>/_processed/<YYYY-MM>/`.
4. Journal entry appended to `<parent>/JOURNAL.md` and `<parent>/journal.jsonl`.
5. **Bonus**: any future calendar events extracted from the document
   automatically appear on the user's Slack proposal dashboard via
   event-aggregator's existing flow.

## Install (on the mini)

```
git pull
cd ~/Home-Tools/nas-intake
bash install.sh
```

Idempotent. Re-run after `git pull` to pick up new code.

## Files

- `watcher.py` — entry point; one tick per invocation.
- `discovery.py` — auto-discover `~/Share1/**/intake/` folders.
- `nas_mount.py` — `_nas_available()` + `ensure_mounted()` (auto-remount via `Mac-mini/scripts/mount-nas.sh`).
- `processor.py` — per-file pipeline: subprocess to event-aggregator → metadata → parent-rooted filing → archive source → purge staging.
- `journal.py` — atomic per-parent journal append (Markdown + JSONL).
- `state.py` — local stability gate + dedup history.
- `config.py` — single source of truth = `event-aggregator/.env`.

## Logs

`/Users/homeserver/Library/Logs/home-tools-nas-intake.log` (and `-error.log`).

## v1 limitations

- HEIC files: deferred to v2 (logged + left in place).
- Mismatch detection / hold-in-_review with Slack reactions: deferred to v2.
- Quarantine after N failures: deferred to v2 (failed files retry every tick).
