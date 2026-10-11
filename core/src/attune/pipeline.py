"""The pipeline (orchestration).

Wires the pieces together for a time range:

    sources → store → align → detect → select → coach → result

It is deliberately thin: every step lives in its own module, and each dependency can be
injected (for tests) or built from :class:`Settings` (for normal runs).
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from attune.align import Aligner
from attune.coach import build_coach
from attune.coach.coach import Coach
from attune.config import Settings, get_settings
from attune.detect import DEFAULT_DETECTORS
from attune.detect.base import Detector
from attune.models import Moment, Recommendation
from attune.sources import build_conversation_source, build_vitals_source
from attune.store import Store


def now_ms() -> int:
    """Current time as UTC epoch milliseconds (ADR-008)."""
    return int(time.time() * 1000)


def default_window(lookback_minutes: int = 60) -> tuple[int, int]:
    """A convenient [start, end] window ending now — covers the synthetic session."""
    end = now_ms()
    return end - lookback_minutes * 60_000, end


class PipelineResult(BaseModel):
    """Everything a run produced — JSON-serializable for the CLI and API."""

    start_ms: int
    end_ms: int
    coach_backend: str
    n_conversations: int = 0
    n_utterances: int = 0
    n_vitals: int = 0
    moments: list[Moment] = Field(default_factory=list)
    salient_moments: list[Moment] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class Pipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        store: Store | None = None,
        detectors: list[Detector] | None = None,
        coach: Coach | None = None,
    ):
        self.settings = settings or get_settings()
        self.store = store or Store(self.settings.db_path)
        self.detectors = detectors if detectors is not None else DEFAULT_DETECTORS
        self.coach = coach or build_coach(self.settings)
        self.aligner = Aligner(
            align_window_ms=self.settings.align_window_ms,
            baseline_window_ms=self.settings.baseline_window_ms,
        )

    def run(self, start_ms: int, end_ms: int) -> PipelineResult:
        # 1. Conversations → store (idempotent upsert).
        conv_source = build_conversation_source(self.settings)
        conversations = list(conv_source.fetch(start_ms, end_ms))
        if conversations:
            self.store.upsert_conversations(conversations)
        conversations = self.store.get_conversations(start_ms, end_ms)

        # 2. Vitals → store. The "api" source means the companion app already pushed them
        #    into the store (ADR-009), so we skip the pull and just read the store.
        if self.settings.vitals_source != "api":
            vit_source = build_vitals_source(self.settings)
            pulled = list(vit_source.fetch(start_ms, end_ms))
            if pulled:
                self.store.add_vitals(pulled)
        vitals = self.store.get_vitals(start_ms, end_ms)

        # 3. Align → moments.
        moments = self.aligner.build_moments(conversations, vitals)

        # 4. Detect → annotate moments in place.
        for detector in self.detectors:
            detector.run(moments)

        # 5. Select the salient moments, most-salient first, capped for the coach.
        salient = sorted(
            (m for m in moments if m.salience > 0), key=lambda m: m.salience, reverse=True
        )[: self.settings.coach_max_moments]

        # 6. Coach → recommendations (free TemplateCoach by default; ADR-017).
        recommendations = self.coach.generate(salient)

        return PipelineResult(
            start_ms=start_ms,
            end_ms=end_ms,
            coach_backend=self.settings.coach_backend,
            n_conversations=len(conversations),
            n_utterances=sum(len(c.utterances) for c in conversations),
            n_vitals=len(vitals),
            moments=moments,
            salient_moments=salient,
            recommendations=recommendations,
        )
