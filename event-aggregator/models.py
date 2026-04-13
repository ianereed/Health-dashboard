"""
Core data models for the local event aggregator pipeline.

Privacy note: body_text on RawMessage is PRIVATE — never log, print, or surface it.
All development/testing uses synthetic data from tests/mock_data.py only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawMessage:
    id: str
    source: str  # "gmail"|"gcal"|"slack"|"imessage"|"whatsapp"|"discord"|"messenger"|"instagram"
    timestamp: datetime  # always UTC-aware; connectors normalize before returning
    body_text: str       # PRIVATE — never log or surface
    metadata: dict[str, Any] = field(default_factory=dict)  # sender, subject, channel only


@dataclass
class CandidateEvent:
    title: str
    start_dt: datetime       # UTC-aware
    end_dt: datetime | None
    location: str | None
    confidence: float        # 0.0–1.0
    source: str
    source_id: str

    def __post_init__(self) -> None:
        # Clamp confidence to valid range
        self.confidence = max(0.0, min(1.0, self.confidence))
        # Sanitize title
        self.title = self.title[:200].strip()


@dataclass
class WrittenEvent:
    gcal_event_id: str
    fingerprint: str  # sha256(title.lower() + date_str)
    candidate: CandidateEvent
