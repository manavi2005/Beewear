"""Abstract source interfaces (Strategy pattern, ADR-007/010).

A source's only job is to yield canonical-model objects for a time range. How it gets
them — live REST, a recorded fixture, a generator, an XML export — is its own business.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from attune.models import Conversation, VitalSample


class ConversationSource(ABC):
    """Yields :class:`Conversation` objects (with utterances) overlapping a time range."""

    name: str = "conversation"

    @abstractmethod
    def fetch(self, start_ms: int, end_ms: int) -> Iterable[Conversation]:
        """Return conversations overlapping ``[start_ms, end_ms]`` (UTC epoch ms)."""
        raise NotImplementedError


class VitalsSource(ABC):
    """Yields :class:`VitalSample` objects within a time range."""

    name: str = "vitals"

    @abstractmethod
    def fetch(self, start_ms: int, end_ms: int) -> Iterable[VitalSample]:
        """Return vital samples with ``start_ms <= ts_ms <= end_ms`` (UTC epoch ms)."""
        raise NotImplementedError


class EmptyVitalsSource(VitalsSource):
    """A no-op vitals source.

    Used when ``vitals_source == "api"`` (ADR-009): the companion app pushes samples into
    the store directly, so the pipeline reads them from the store rather than pulling here.
    """

    name = "empty"

    def fetch(self, start_ms: int, end_ms: int) -> Iterable[VitalSample]:
        return []
