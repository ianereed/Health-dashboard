"""
Local Event Aggregator — main entry point.

Usage:
  python main.py                          # full run, all sources
  python main.py --mock                   # use synthetic data only (safe for demos)
  python main.py --dry-run                # extract + dedup but don't write to calendar
  python main.py --source gmail,slack     # run specific sources only
  python main.py --digest-only            # skip extraction; just send digest
  python main.py --mock --dry-run         # Phase 1 test (no external calls except Ollama)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

import config
import extractor
import state as state_module
from connectors.discord_conn import DiscordConnector
from connectors.gmail import GmailConnector
from connectors.google_calendar import GoogleCalendarConnector
from connectors.imessage import IMessageConnector
from connectors.notifications import NotificationCenterConnector
from connectors.slack import SlackConnector
from connectors.whatsapp import WhatsAppConnector
from dedup import fingerprint, is_duplicate
from logs.event_log import record as log_event
from models import CandidateEvent
from writers import google_calendar as gcal_writer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Registry: source name → connector class
_CONNECTOR_REGISTRY = {
    "gmail": GmailConnector,
    "gcal": GoogleCalendarConnector,
    "slack": SlackConnector,
    "imessage": IMessageConnector,
    "whatsapp": WhatsAppConnector,
    "discord": DiscordConnector,
    # Messenger + Instagram share one connector
    "messenger": NotificationCenterConnector,
    "instagram": NotificationCenterConnector,
}

_ALL_SOURCES = [
    "gmail", "gcal", "slack", "imessage", "whatsapp", "discord", "messenger", "instagram"
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Event Aggregator")
    parser.add_argument("--mock", action="store_true", help="Use synthetic test data only")
    parser.add_argument("--dry-run", action="store_true", help="Extract but do not write to GCal")
    parser.add_argument("--source", default="", help="Comma-separated sources to run (default: all)")
    parser.add_argument("--digest-only", action="store_true", help="Send digests, skip extraction")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.mock and not extractor.check_ollama_available():
        logger.warning(
            "Ollama is not running at %s — event extraction will be skipped. "
            "Start Ollama or use --mock for testing.",
            config.OLLAMA_BASE_URL,
        )

    sources = [s.strip() for s in args.source.split(",") if s.strip()] if args.source else _ALL_SOURCES

    if not args.mock:
        try:
            config.validate_for_sources(sources)
        except EnvironmentError as exc:
            logger.error("%s", exc)
            return 1

    state = state_module.load()

    if args.digest_only:
        _send_digests(state)
        state_module.save(state)
        return 0

    # ── Collect messages from all selected sources ───────────────────────────
    all_messages = []
    seen_connectors: set[type] = set()

    for source in sources:
        connector_cls = _CONNECTOR_REGISTRY.get(source)
        if connector_cls is None:
            logger.warning("Unknown source: %s — skipping", source)
            continue
        # Notification Center connector covers both messenger + instagram; instantiate once
        if connector_cls in seen_connectors:
            continue
        seen_connectors.add(connector_cls)

        connector = connector_cls()
        since = state.last_run(source)
        logger.info("Fetching %s since %s (mock=%s)", source, since.date(), args.mock)
        msgs = connector.fetch(since=since, mock=args.mock)
        logger.info("  → %d message(s)", len(msgs))
        all_messages.extend(msgs)

    # ── Extract candidate events ─────────────────────────────────────────────
    all_candidates: list[CandidateEvent] = []
    if extractor.check_ollama_available() or args.mock:
        for msg in all_messages:
            if state.is_seen(msg.source, msg.id):
                continue
            candidates = extractor.extract(msg)
            all_candidates.extend(candidates)
            state.mark_seen(msg.source, msg.id)
    else:
        logger.warning("Skipping extraction — Ollama unavailable")

    logger.info("Extraction complete: %d candidate event(s) total", len(all_candidates))

    # ── Dedup + write ────────────────────────────────────────────────────────
    written_count = 0
    for candidate in all_candidates:
        fp = fingerprint(candidate)
        if state.has_fingerprint(fp):
            logger.debug("skip duplicate: %r (fingerprint match)", candidate.title)
            continue

        # Build list of already-written candidates for fuzzy dedup
        # (simplified: check fingerprints only at this stage; GCal pre-write check in Phase 2)
        written = gcal_writer.write_event(candidate, dry_run=args.dry_run)
        if written:
            state.add_fingerprint(fp)
            log_event(written, action="created")
            written_count += 1
        elif args.dry_run:
            logger.info(
                "DRY RUN: %r on %s (confidence=%.2f, source=%s)",
                candidate.title,
                candidate.start_dt.date(),
                candidate.confidence,
                candidate.source,
            )

    logger.info(
        "Run complete: %d candidate(s), %d written%s",
        len(all_candidates),
        written_count,
        " [DRY RUN]" if args.dry_run else "",
    )

    # ── Update last_run timestamps ───────────────────────────────────────────
    for source in sources:
        state.set_last_run(source)

    state_module.save(state)

    # ── Send digests ─────────────────────────────────────────────────────────
    if not args.dry_run and not args.mock:
        _send_digests(state)

    return 0


def _send_digests(state) -> None:
    """Placeholder: will call digest.send_daily_digest / send_weekly_digest in Phase 6."""
    # TODO (Phase 6): fetch year-ahead calendar, run analysis, send digests
    logger.debug("digest sending not yet implemented (Phase 6)")


if __name__ == "__main__":
    sys.exit(main())
