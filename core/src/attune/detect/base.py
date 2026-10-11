"""Detector interface (ADR-005).

A detector inspects one :class:`Moment` (with the full list available for cross-moment
reasoning, e.g. repeated topics) and returns zero or more :class:`Signal` annotations. Add a
vertical (Composure AI, NeuroLearn) later by writing new detectors — the core does not change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from attune.models import Moment, Signal


class Detector(ABC):
    name: str = "detector"

    @abstractmethod
    def detect(self, moment: Moment, all_moments: list[Moment]) -> list[Signal]:
        """Return signals for ``moment``. ``all_moments`` is provided for context."""
        raise NotImplementedError

    def run(self, moments: list[Moment]) -> None:
        """Annotate every moment in place with this detector's signals."""
        for m in moments:
            m.signals.extend(self.detect(m, moments))
