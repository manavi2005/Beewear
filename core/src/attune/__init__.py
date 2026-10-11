"""Attune — concept-agnostic base layer for an adaptive AI coach (ADR-016).

Combines *what you discussed* (Bee conversation context) with *how your body responded*
(Apple Watch physiology), aligned in time, to surface notable moments and generate hedged,
personalized, baseline-relative coaching.

See ``docs/ARCHITECTURE.md`` for the big picture and ``docs/DECISIONS.md`` for why.
"""

from __future__ import annotations

__version__ = "0.1.0"

from attune.models import (  # noqa: E402
    CheckIn,
    Conversation,
    Moment,
    Recommendation,
    Session,
    Signal,
    Utterance,
    VitalDelta,
    VitalSample,
    VitalType,
)

__all__ = [
    "__version__",
    "CheckIn",
    "Conversation",
    "Moment",
    "Recommendation",
    "Session",
    "Signal",
    "Utterance",
    "VitalDelta",
    "VitalSample",
    "VitalType",
]
