"""Tier 3 — connector contract conformance.

Every connector must:
  - return a (list[RawMessage], ConnectorStatus) tuple
  - never raise (mock and live paths)
  - return ok() with mock=True
  - declare a non-empty source_name

These are smoke-level checks; per-connector behavior tests live in
their own files (test_extractor, test_dedup, etc.).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from connectors.base import ConnectorStatus, ConnectorStatusCode
from connectors.gmail import GmailConnector
from connectors.google_calendar import GoogleCalendarConnector
from connectors.slack import SlackConnector
from connectors.imessage import IMessageConnector
from connectors.whatsapp import WhatsAppConnector
from connectors.discord_conn import DiscordConnector
from connectors.notifications import NotificationCenterConnector


_CONNECTOR_CLASSES = [
    GmailConnector,
    GoogleCalendarConnector,
    SlackConnector,
    IMessageConnector,
    WhatsAppConnector,
    DiscordConnector,
    NotificationCenterConnector,
]


def _yesterday() -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(days=1)


@pytest.mark.parametrize(
    "cls", _CONNECTOR_CLASSES, ids=[c.__name__ for c in _CONNECTOR_CLASSES],
)
def test_connector_returns_tuple_with_mock(cls):
    connector = cls()
    result = connector.fetch(since=_yesterday(), mock=True)
    assert isinstance(result, tuple), f"{cls.__name__}.fetch did not return a tuple"
    assert len(result) == 2, f"{cls.__name__}.fetch did not return (messages, status)"
    messages, status = result
    assert isinstance(messages, list)
    assert isinstance(status, ConnectorStatus)
    assert status.code == ConnectorStatusCode.OK


@pytest.mark.parametrize(
    "cls", _CONNECTOR_CLASSES, ids=[c.__name__ for c in _CONNECTOR_CLASSES],
)
def test_connector_has_source_name(cls):
    connector = cls()
    assert connector.source_name, f"{cls.__name__} has empty source_name"
    assert isinstance(connector.source_name, str)


def _scrub_credentials(monkeypatch):
    """Force each connector down its no-creds / no-DB / unsupported_os branch."""
    import config
    monkeypatch.setattr(config, "SLACK_BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "SLACK_MONITOR_CHANNELS", [], raising=False)
    monkeypatch.setattr(config, "DISCORD_BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "DISCORD_MONITOR_CHANNELS", [], raising=False)
    monkeypatch.setattr(config, "GMAIL_TOKEN_JSON", "/nonexistent/gmail_token.json", raising=False)
    monkeypatch.setattr(config, "GCAL_TOKEN_JSON", "/nonexistent/gcal_token.json", raising=False)
    monkeypatch.setattr(config, "GMAIL_CREDENTIALS_JSON", "/nonexistent/oauth.json", raising=False)
    monkeypatch.setattr(config, "IMESSAGE_DB_PATH", "/nonexistent/chat.db", raising=False)
    monkeypatch.setattr(config, "WHATSAPP_DB_PATH", "/nonexistent/ChatStorage.sqlite", raising=False)
    # NotificationCenter: force the unsupported_os branch deterministically.
    from connectors import notifications as nc
    monkeypatch.setattr(nc, "_NC_DB_GLOB", "/nonexistent/NotificationCenter/*.db", raising=False)
    # google_auth: bypass keyring fallback by pointing the service name at a
    # junk key that won't have any tokens stashed locally. Otherwise the
    # laptop's live keyring tokens make Gmail/GCal succeed.
    from connectors import google_auth
    monkeypatch.setattr(
        google_auth, "_KEYRING_SERVICE",
        "home-tools-event-aggregator-test-nonexistent",
        raising=False,
    )


@pytest.mark.parametrize(
    "cls", _CONNECTOR_CLASSES, ids=[c.__name__ for c in _CONNECTOR_CLASSES],
)
def test_connector_does_not_raise_on_live_fetch(cls, monkeypatch):
    """Live (non-mock) fetch must never raise. With creds scrubbed, every
    connector hits a known no-creds / no-DB branch and returns a non-OK
    ConnectorStatus — verifying the no-raise contract end-to-end.
    """
    _scrub_credentials(monkeypatch)

    connector = cls()
    messages, status = connector.fetch(since=_yesterday(), mock=False)
    assert isinstance(messages, list)
    assert isinstance(status, ConnectorStatus)
    assert status.code in ConnectorStatusCode  # Enum membership
    # With credentials scrubbed, every connector should return NON-OK.
    assert status.code != ConnectorStatusCode.OK, (
        f"{cls.__name__} returned OK with all credentials scrubbed — likely a "
        f"missing branch in fetch()"
    )
