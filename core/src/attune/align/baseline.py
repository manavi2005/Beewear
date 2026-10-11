"""Personal-baseline computation (ADR-011, ETHICS rule 1).

Everything here is strictly *relative to the user's own recent readings*. There are no
population thresholds and no mapping to emotional or cognitive states — only words like
"elevated", "lowered", and "typical", with an optional standardized distance ``z``.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from attune.models import VitalDelta, VitalSample, VitalType


class Baseline:
    """Answers: "relative to this person's own recent readings, is this value unusual?"

    A reading is called ``elevated`` / ``lowered`` only when it sits at least ``z_thresh``
    standard deviations from the personal baseline; otherwise it is ``typical``.
    """

    def __init__(self, samples: list[VitalSample], z_thresh: float = 1.0):
        self.z_thresh = z_thresh
        self._by_type: dict[VitalType, list[tuple[int, float]]] = defaultdict(list)
        for s in samples:
            self._by_type[s.type].append((s.ts_ms, s.value))
        for series in self._by_type.values():
            series.sort(key=lambda p: p[0])

    def _values_in(self, vtype: VitalType, lo_ms: int, hi_ms: int) -> list[float]:
        return [v for ts, v in self._by_type.get(vtype, []) if lo_ms <= ts <= hi_ms]

    def window_mean(self, vtype: VitalType, lo_ms: int, hi_ms: int) -> float | None:
        vals = self._values_in(vtype, lo_ms, hi_ms)
        return statistics.fmean(vals) if vals else None

    def describe(
        self,
        vtype: VitalType,
        value: float,
        at_ms: int,
        baseline_window_ms: int,
    ) -> VitalDelta | None:
        """Describe ``value`` at ``at_ms`` relative to the personal baseline for ``vtype``.

        The baseline is drawn from the ``baseline_window_ms`` leading up to ``at_ms``. If that
        leading window is too sparse, we fall back to the whole available series so the demo
        still produces a sensible comparison.
        """
        baseline_vals = self._values_in(vtype, at_ms - baseline_window_ms, at_ms)
        if len(baseline_vals) < 3:
            baseline_vals = [v for _, v in self._by_type.get(vtype, [])]
        if len(baseline_vals) < 3:
            return None

        mean = statistics.fmean(baseline_vals)
        stdev = statistics.pstdev(baseline_vals)

        if stdev > 1e-9:
            z = (value - mean) / stdev
            direction = (
                "elevated" if z >= self.z_thresh
                else "lowered" if z <= -self.z_thresh
                else "typical"
            )
        else:
            # Flat baseline (no variance): fall back to a percent-change threshold so a
            # clear spike/drop still reads as unusual. z is left undefined (None).
            z = None
            pct = (value - mean) / mean if abs(mean) > 1e-9 else 0.0
            direction = (
                "elevated" if pct >= 0.10
                else "lowered" if pct <= -0.10
                else "typical"
            )

        return VitalDelta(
            type=vtype,
            value=round(value, 2),
            baseline=round(mean, 2),
            direction=direction,
            z=round(z, 2) if z is not None else None,
        )
