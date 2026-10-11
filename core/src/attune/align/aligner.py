"""The time-alignment engine (ADR-008).

Joins each utterance to the physiological samples around it and attaches a baseline-relative
description per vital type. The output — a list of :class:`Moment` — is the unit the detectors
and coach operate on.

This module is pure and deterministic: given the same inputs it always produces the same
moments, which makes it trivial to test.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from attune.align.baseline import Baseline
from attune.models import CheckIn, Conversation, Moment, VitalDelta, VitalSample, VitalType


class Aligner:
    """Builds :class:`Moment` objects by joining utterances with nearby vitals."""

    def __init__(self, align_window_ms: int = 45_000, baseline_window_ms: int = 600_000):
        self.align_window_ms = align_window_ms
        self.baseline_window_ms = baseline_window_ms

    def build_moments(
        self,
        conversations: list[Conversation],
        vitals: list[VitalSample],
        checkins: list[CheckIn] | None = None,
    ) -> list[Moment]:
        utterances = sorted(
            (u for c in conversations for u in c.utterances), key=lambda u: u.ts_ms
        )
        baseline = Baseline(vitals)
        vitals_sorted = sorted(vitals, key=lambda s: s.ts_ms)
        checkins_sorted = sorted(checkins or [], key=lambda c: c.ts_ms)

        moments: list[Moment] = []
        for utt in utterances:
            window = self._vitals_in_window(vitals_sorted, utt.ts_ms)
            context = self._describe_window(baseline, window, utt.ts_ms)
            moments.append(
                Moment(
                    ts_ms=utt.ts_ms,
                    utterance=utt,
                    vitals_window=window,
                    vitals_context=context,
                )
            )
        self._assign_checkins(moments, checkins_sorted)
        return moments

    def _assign_checkins(self, moments: list[Moment], checkins: list[CheckIn]) -> None:
        """Bind each self-report to its single nearest moment (one-to-one).

        A check-in ("that felt hard: 4/5") refers to one thing, so it must not be claimed by
        every nearby utterance. We assign each check-in to the closest moment within the
        alignment window; later ties for the same moment keep the nearer check-in.
        """
        if not moments:
            return
        best_dt: dict[int, int] = {}
        for c in checkins:
            nearest: Moment | None = None
            nearest_dt = self.align_window_ms + 1
            for m in moments:
                dt = abs(m.ts_ms - c.ts_ms)
                if dt < nearest_dt:
                    nearest, nearest_dt = m, dt
            if nearest is not None and nearest_dt < best_dt.get(id(nearest), nearest_dt + 1):
                nearest.checkin = c
                best_dt[id(nearest)] = nearest_dt

    # ── helpers ──────────────────────────────────────────────────────────────
    def _vitals_in_window(self, vitals_sorted: list[VitalSample], at_ms: int) -> list[VitalSample]:
        lo, hi = at_ms - self.align_window_ms, at_ms + self.align_window_ms
        return [s for s in vitals_sorted if lo <= s.ts_ms <= hi]

    def _describe_window(
        self, baseline: Baseline, window: list[VitalSample], at_ms: int
    ) -> dict[VitalType, VitalDelta]:
        by_type: dict[VitalType, list[float]] = defaultdict(list)
        for s in window:
            by_type[s.type].append(s.value)

        context = {}
        for vtype, values in by_type.items():
            representative = statistics.fmean(values)
            delta = baseline.describe(vtype, representative, at_ms, self.baseline_window_ms)
            if delta is not None:
                context[vtype] = delta
        return context
