"""Canonical, source-agnostic domain model (ADR-007).

Every adapter translates its source's native shape into these types at the boundary.
Nothing downstream of a source adapter ever sees raw Bee / HealthKit JSON.

Golden rule (ADR-008): all timestamps are ``ts_ms`` — **UTC epoch milliseconds (int)**.

Deliberate absence: there is no ``emotion``, ``stress``, or ``confused`` field anywhere
in this model. Physiological signals are described only relative to a personal baseline
(see ``VitalDelta`` and ``docs/ETHICS.md``, ADR-011).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field


# ──────────────────────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────────────────────
class VitalType(str, Enum):
    """Physiological sample types we accept from Apple HealthKit (ADR-006)."""

    heart_rate = "heart_rate"
    hrv_sdnn = "hrv_sdnn"
    respiratory_rate = "respiratory_rate"
    wrist_temperature = "wrist_temperature"
    sleep = "sleep"
    movement = "movement"


Direction = Literal["elevated", "lowered", "typical"]


# ──────────────────────────────────────────────────────────────────────────────
# Conversation side (from Bee)
# ──────────────────────────────────────────────────────────────────────────────
class Utterance(BaseModel):
    """One spoken line from a Bee conversation transcript."""

    id: str
    ts_ms: int = Field(..., description="Start time, UTC epoch milliseconds.")
    speaker: str = Field("", description='e.g. "me", "other", or a raw source label.')
    text: str = ""
    conversation_id: str | None = None


class Conversation(BaseModel):
    """A grouped set of utterances from Bee."""

    id: str
    start_ms: int
    end_ms: int
    summary: str | None = None
    utterances: list[Utterance] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Physiology side (from Apple Watch / HealthKit)
# ──────────────────────────────────────────────────────────────────────────────
class VitalSample(BaseModel):
    """One physiological reading.

    This model *is* the ``POST /ingest/vitals`` request schema (ADR-009): the companion
    app serializes exactly these fields.
    """

    type: VitalType
    ts_ms: int = Field(..., description="Sample start, UTC epoch milliseconds.")
    end_ms: int | None = Field(None, description="For interval samples such as sleep.")
    value: float
    unit: str = ""
    source: str = Field("unknown", description='"apple_watch" | "health_export" | "synthetic"')


class CheckIn(BaseModel):
    """A user self-report. First-class and outranks any inferred signal (ETHICS rule 4)."""

    ts_ms: int
    prompt: str = ""
    value: float | None = None
    label: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Analysis products
# ──────────────────────────────────────────────────────────────────────────────
class Session(BaseModel):
    """A bounded analysis window. Labels are caller-provided, never inferred."""

    id: str
    start_ms: int
    end_ms: int
    label: str | None = None


class VitalDelta(BaseModel):
    """A strictly baseline-relative description of a vital in a window (ADR-011).

    ``direction`` uses relative wording only — never an emotional or clinical claim.
    """

    type: VitalType
    value: float
    baseline: float
    direction: Direction
    z: float | None = Field(None, description="Optional standardized distance from baseline.")


class Signal(BaseModel):
    """A detector's annotation on a moment."""

    kind: str
    detector: str
    weight: float = Field(0.5, ge=0.0, le=1.0, description="Salience, 0–1.")
    evidence: str = ""


class Moment(BaseModel):
    """An utterance plus its time-aligned physiological context and detector signals."""

    ts_ms: int
    utterance: Utterance
    vitals_window: list[VitalSample] = Field(default_factory=list)
    vitals_context: dict[VitalType, VitalDelta] = Field(default_factory=dict)
    checkin: CheckIn | None = Field(
        None, description="The user's own self-report nearest this moment (authoritative)."
    )
    signals: list[Signal] = Field(default_factory=list)

    @computed_field  # serialized into JSON so the dashboard/API can rank moments
    @property
    def salience(self) -> float:
        """Total salience of attached signals — used to rank moments for the coach."""
        return sum(s.weight for s in self.signals)


class Recommendation(BaseModel):
    """Coach output. Guaranteed guardrail-compliant before it reaches a caller."""

    moment_ts_ms: int
    title: str
    body: str
    basis: list[str] = Field(default_factory=list)
    generated_by: Literal["claude", "ollama", "template"] = "template"
