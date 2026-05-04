"""
Job-runner functions imported by jobs/kinds/event_aggregator_{text,vision}.py.

After Phase 12.7/12.8b the long-running worker loop is retired. Processing is
handled by huey kinds. _run_text_job and _run_ocr_job live here (not in the
kinds themselves) so they can stay in the event-aggregator venv and call
extractor/state/notifier code directly without crossing venv boundaries.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

import config
import tz_utils

logger = logging.getLogger(__name__)


# ── Ollama lifecycle (load / unload by setting keep_alive) ────────────────────

def _ollama_unload(model: str) -> None:
    """Best-effort unload — set keep_alive=0 so Ollama frees the model now."""
    try:
        requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json={"model": model, "keep_alive": 0, "prompt": "", "stream": False},
            timeout=10,
        )
        logger.info("worker: unloaded model %s", model)
    except Exception as exc:
        logger.warning("worker: unload of %s failed (best effort): %s", model, exc)


def _ollama_warmup(model: str, num_ctx: int, keep_alive: str = "-1") -> None:
    """Best-effort warmup — issue an empty generate so the model is resident."""
    try:
        requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": "",
                "stream": False,
                "keep_alive": keep_alive,
                "options": {"num_ctx": num_ctx},
            },
            timeout=120,
        )
        logger.info("worker: warmed model %s (ctx=%d)", model, num_ctx)
    except Exception as exc:
        logger.warning("worker: warmup of %s failed (best effort): %s", model, exc)


# ── Job runners ───────────────────────────────────────────────────────────────

def _run_text_job(state, job: dict) -> None:
    """Run extraction for one queued message and persist results."""
    import extractor
    from analyzers import calendar_analyzer
    from connectors import google_auth
    from googleapiclient.discovery import build
    from models import RawMessage, CandidateEvent

    source = job["source"]
    msg_id = job["id"]
    logger.info("worker: starting text job source=%s id=%s", source, msg_id)

    # Skip if extraction already happened (re-running over a partially-drained queue)
    if state.is_seen(source, msg_id):
        logger.debug("worker: %s/%s already seen — skipping", source, msg_id)
        return

    try:
        ts = datetime.fromisoformat(job["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, KeyError):
        ts = datetime.now(timezone.utc)

    msg = RawMessage(
        id=msg_id,
        source=source,
        timestamp=ts,
        body_text=job.get("body_text", ""),
        metadata=job.get("metadata") or {},
    )

    # Pre-classifier: skip the 16k-ctx call on obvious non-event noise.
    # "maybe" falls through; "no" short-circuits.
    verdict, reason = extractor.pre_classify(msg)
    logger.info("worker: pre-classify %s/%s → %s", source, msg_id, verdict)
    if verdict == "no":
        state.mark_seen(source, msg_id)
        return

    # Refresh calendar context per-job — the upcoming-events list may have
    # changed between when we enqueued and when we extract.
    calendar_context = ""
    try:
        import concurrent.futures
        creds = google_auth.get_credentials(
            scopes=["https://www.googleapis.com/auth/calendar.events"],
            token_path=config.GCAL_TOKEN_JSON,
            credentials_path=config.GMAIL_CREDENTIALS_JSON,
            keyring_key="gcal_token",
        )
        svc = build("calendar", "v3", credentials=creds)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
            _fut = _ex.submit(calendar_analyzer.fetch_upcoming, svc, weeks=config.CALENDAR_CONTEXT_WEEKS)
            upcoming = _fut.result(timeout=15)
        # Lightweight inline format — same shape as main._format_calendar_context
        lines = []
        for e in upcoming:
            if getattr(e, "is_all_day", False):
                continue
            start = e.start_dt.strftime("%b %-d %-I:%M%p").lower()
            lines.append(f"- {start}: {e.title}")
        calendar_context = "\n".join(lines)
        # Append invite_context block so the LLM knows about pending native
        # GCal invites (already on primary, never written to weekend).
        import main as _main_mod
        invite_block = _main_mod.format_invite_context_block(state)
        if invite_block:
            calendar_context = (
                calendar_context + "\n\n" + invite_block
                if calendar_context else invite_block
            )
    except concurrent.futures.TimeoutError:
        logger.warning("worker: calendar context fetch timed out (15s) — proceeding without context")
    except Exception as exc:
        logger.warning("worker: calendar context fetch failed: %s", exc)

    events, todos = extractor.extract(msg, calendar_context=calendar_context)
    logger.info(
        "worker: extracted %s/%s → %d event(s), %d todo(s)",
        source, msg_id, len(events), len(todos),
    )

    # Hand off to the existing main.py paths via direct function calls.
    # We avoid duplicating the proposal/auto branching here.
    import main as main_module
    # _propose_events / _auto_create_events expect lists; pass single message's worth.
    snapshot = state.calendar_snapshot()
    if config.EVENT_APPROVAL_MODE == "propose":
        main_module._propose_events(events, state, snapshot, dry_run=False, mock=False)
        # Refresh dashboard after each job so the user sees updates immediately.
        if events:
            today_str = tz_utils.today_user_str()
            from notifiers import slack_notifier
            all_items = state.get_all_proposal_items_for_dashboard(today_str)
            slack_notifier.post_or_update_dashboard(all_items, state)
    else:
        # Auto mode — needs a get_thread callback for Slack threading.
        from notifiers import slack_notifier as _sn
        thread_ts = None
        def _get_thread() -> str | None:
            nonlocal thread_ts
            if thread_ts is None:
                thread_ts = _sn.get_or_create_day_thread(state)
            return thread_ts
        main_module._auto_create_events(events, state, snapshot, dry_run=False, mock=False, get_thread=_get_thread)

    # Todos
    if todos:
        from dedup import todo_fingerprint
        from writers import todoist_writer
        # Resolve target project once per job — get_or_create_project caches
        # the ID in state.json on first hit. None on API failure → todos go
        # to the user's Todoist inbox per the writer's documented contract.
        project_id = todoist_writer.get_or_create_project(
            config.TODOIST_API_TOKEN, config.TODOIST_PROJECT_NAME, state,
        )
        for todo in todos:
            if todo.confidence < config.TODOIST_TODO_MIN_CONFIDENCE:
                continue
            fp = todo_fingerprint(todo)
            if state.has_todo_fingerprint(fp):
                continue
            ok = todoist_writer.create_task(
                token=config.TODOIST_API_TOKEN,
                project_id=project_id,
                todo=todo,
                dry_run=False,
            )
            if ok:
                state.add_todo_fingerprint(fp)

    state.mark_seen(source, msg_id)


def _run_ocr_job(state, job: dict) -> None:
    """Run OCR / image analysis on a queued file path."""
    from pathlib import Path
    import cli  # reuse the existing single-file pipeline
    logger.info("worker: starting OCR job file=%s", job.get("file_path", ""))
    file_path = Path(job["file_path"])
    if not file_path.exists():
        logger.warning("worker: OCR file not found, dropping: %s", file_path)
        return
    logger.info("worker: OCR job → %s", file_path)
    try:
        cli._cmd_ingest_image(file_path)
    except Exception as exc:
        logger.warning("worker: OCR job failed for %s: %s", file_path, exc)
