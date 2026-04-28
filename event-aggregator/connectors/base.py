"""Abstract base class for all message source connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from models import RawMessage


class ConnectorStatusCode(str, Enum):
    """Outcome of a connector fetch.

    Codes are persisted to state.json verbatim — never rename existing
    values without a migration. Add new codes as needed; the dashboard
    renderer treats anything outside its known set as `unknown_error`.
    """
    OK = "ok"                                # fetched (0+ messages)
    NO_CREDENTIALS = "no_credentials"        # token/key not configured (deferred)
    AUTH_ERROR = "auth_error"                # 401/403/refresh failed — re-auth needed
    PERMISSION_DENIED = "permission_denied"  # macOS FDA missing, file unreadable
    UNSUPPORTED_OS = "unsupported_os"        # platform incompatible (e.g. NC on Sequoia)
    NETWORK_ERROR = "network_error"          # transient — retried next cycle
    SCHEMA_ERROR = "schema_error"            # SQLite columns / API shape changed
    UNKNOWN_ERROR = "unknown_error"          # catchall


@dataclass
class ConnectorStatus:
    """Structured outcome of a single fetch.

    Privacy invariant: `message` MUST NOT contain message bodies, contact
    info, or location strings — this string is rendered to the Slack
    dashboard and persisted to state.json. Stick to: error class names,
    HTTP codes, OS names, missing-config keys, count summaries.
    """
    code: ConnectorStatusCode
    message: str = ""

    @classmethod
    def ok(cls) -> "ConnectorStatus":
        return cls(ConnectorStatusCode.OK)


# Tuple alias used in connector signatures
FetchResult = tuple[list[RawMessage], ConnectorStatus]


class BaseConnector(ABC):
    """
    All connectors implement this interface.

    fetch() must NEVER raise — every exception path maps to a
    `ConnectorStatus` with an appropriate code. Returned RawMessage
    timestamps must always be UTC-aware.
    """

    source_name: str  # class-level constant, matches RawMessage.source values

    @abstractmethod
    def fetch(self, since: datetime, mock: bool = False) -> FetchResult:
        """
        Return (messages, status) — messages newer than `since` plus a
        status describing the fetch outcome. With mock=True, return
        synthetic data and ConnectorStatus.ok().
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source={self.source_name!r})"
