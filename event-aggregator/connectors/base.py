"""Abstract base class for all message source connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from models import RawMessage


class BaseConnector(ABC):
    """
    All connectors implement this interface.
    fetch() must never raise — return [] on any error and log a warning.
    Timestamps on returned RawMessages must always be UTC-aware.
    """

    source_name: str  # class-level constant, matches RawMessage.source values

    @abstractmethod
    def fetch(self, since: datetime, mock: bool = False) -> list[RawMessage]:
        """
        Return messages from this source newer than `since`.
        If mock=True, return synthetic data from tests/mock_data.py instead.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source={self.source_name!r})"
