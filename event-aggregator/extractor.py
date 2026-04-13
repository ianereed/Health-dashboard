"""
Event extractor: sends message body_text to local Ollama and parses the response
into a list of CandidateEvent objects.

Privacy: body_text never appears in logs. Log only source/id/count metadata.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import requests

import config
from models import CandidateEvent, RawMessage

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.5
_TITLE_MAX_CHARS = 200
_UNSAFE_TITLE_RE = re.compile(r"[<>\"'`]|ignore.*instruction|system prompt", re.IGNORECASE)
_FUTURE_YEARS = 2


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _validate_event(raw: dict[str, Any]) -> CandidateEvent | None:
    """Validate and sanitize a single LLM-extracted event dict. Returns None if invalid."""
    try:
        title = str(raw.get("title", "")).strip()[:_TITLE_MAX_CHARS]
        if not title or _UNSAFE_TITLE_RE.search(title):
            return None

        start_str = raw.get("start")
        if not start_str:
            return None
        start_dt = datetime.fromisoformat(str(start_str))
        # Make timezone-aware if naive (assume UTC)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        now = _utcnow()
        if not (now - _years(2) <= start_dt <= now + _years(_FUTURE_YEARS)):
            return None

        end_dt = None
        end_str = raw.get("end")
        if end_str:
            end_dt = datetime.fromisoformat(str(end_str))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            if end_dt <= start_dt:
                end_dt = None

        location = raw.get("location")
        if location:
            location = str(location)[:300].strip() or None

        confidence = float(raw.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        return CandidateEvent(
            title=title,
            start_dt=start_dt,
            end_dt=end_dt,
            location=location,
            confidence=confidence,
            source="",   # filled in by caller
            source_id="",
        )
    except (ValueError, TypeError, KeyError):
        return None


def _years(n: int) -> object:
    from datetime import timedelta
    return timedelta(days=365 * n)


_PROMPT = """\
You are an event extraction assistant. Extract any scheduled events from the message below.
Respond with JSON matching exactly this schema:
{{"events": [{{"title": "...", "start": "YYYY-MM-DDTHH:MM:SS", "end": "... or null",
              "location": "... or null", "confidence": 0.0}}]}}
If no events are found, return: {{"events": []}}

Message:
{body_text}
"""


def _call_ollama(body_text: str) -> list[dict[str, Any]]:
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": _PROMPT.format(body_text=body_text),
        "stream": False,
        "format": "json",
    }
    resp = requests.post(
        f"{config.OLLAMA_BASE_URL}/api/generate",
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json().get("response", "")
    data = json.loads(text)
    return data.get("events", [])


def extract(message: RawMessage) -> list[CandidateEvent]:
    """
    Extract candidate events from a single RawMessage via Ollama.
    Returns an empty list on any failure — never raises.
    """
    for attempt in range(2):
        try:
            raw_events = _call_ollama(message.body_text)
            break
        except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
            if attempt == 0:
                logger.warning(
                    "extractor: attempt %d failed for source=%s id=%s: %s",
                    attempt + 1, message.source, message.id, type(exc).__name__,
                )
            else:
                logger.warning(
                    "extractor: skipping source=%s id=%s after 2 failures",
                    message.source, message.id,
                )
                return []

    candidates = []
    for raw in raw_events:
        event = _validate_event(raw)
        if event is None:
            continue
        if event.confidence < _CONFIDENCE_THRESHOLD:
            continue
        event.source = message.source
        event.source_id = message.id
        candidates.append(event)

    logger.debug(
        "extractor: source=%s id=%s → %d candidate(s)",
        message.source, message.id, len(candidates),
    )
    return candidates


def check_ollama_available() -> bool:
    """Returns True if Ollama is reachable. Called at startup."""
    try:
        resp = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False
