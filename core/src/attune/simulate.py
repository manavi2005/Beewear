"""A software stand-in for the Apple Watch (ADR-023).

`WatchSimulator` produces realistic `VitalSample`s so you can exercise the whole
server → store → dashboard loop **before** the Xcode companion app is built, and demo even
if the Watch isn't cooperating. It is the same canonical schema the real app posts
(`source="simulated_watch"`), so nothing downstream can tell the difference.

Used by `attune simulate-watch` (see cli.py).
"""

from __future__ import annotations

import random

from attune.models import VitalSample, VitalType


class WatchSimulator:
    """A gentle random-walk heart-rate model with optional elevation.

    `tick()` returns the sample(s) for "now" (live streaming); `backfill()` returns a whole
    recent series in one shot (instant dashboard data).
    """

    def __init__(self, resting_bpm: float = 72.0, seed: int = 7):
        self.resting = resting_bpm
        self.rng = random.Random(seed)
        self.hr = resting_bpm
        self._ticks = 0

    # ── live streaming ────────────────────────────────────────────────────────
    def tick(self, now_ms: int, *, elevated: bool = False) -> list[VitalSample]:
        """One step of live data. HR every call; HRV + respiratory roughly every ~30s."""
        target = self.resting + (30.0 if elevated else 0.0)
        # Ease toward the target with a little noise (a plausible HR trajectory).
        self.hr += (target - self.hr) * 0.3 + self.rng.uniform(-2.0, 2.0)
        self.hr = max(45.0, min(190.0, self.hr))
        self._ticks += 1

        samples = [self._hr(now_ms, self.hr)]
        if self._ticks % 15 == 0:  # ~every 30s at a 2s cadence
            samples.append(self._hrv(now_ms, elevated))
            samples.append(self._resp(now_ms, elevated))
        return samples

    # ── backfill a window ─────────────────────────────────────────────────────
    def backfill(
        self, end_ms: int, minutes: int = 10, hr_step_s: int = 5, elevate_frac: float = 0.7
    ) -> list[VitalSample]:
        """A realistic recent series ending at ``end_ms``, with one elevation bump.

        ``elevate_frac`` places the bump that far through the window (0..1).
        """
        start_ms = end_ms - minutes * 60_000
        elevate_at = start_ms + int((end_ms - start_ms) * elevate_frac)
        samples: list[VitalSample] = []
        t = start_ms
        while t <= end_ms:
            arousal = max(0.0, 1.0 - abs(t - elevate_at) / 120_000)  # ~2-min bump
            hr = self.resting + self.rng.uniform(-3.0, 3.0) + 30.0 * arousal
            samples.append(self._hr(t, hr))
            t += hr_step_s * 1000
        t = start_ms
        while t <= end_ms:
            arousal = max(0.0, 1.0 - abs(t - elevate_at) / 120_000)
            samples.append(self._hrv(t, arousal > 0.4))
            samples.append(self._resp(t, arousal > 0.4))
            t += 60_000
        return samples

    # ── sample builders ──────────────────────────────────────────────────────
    def _hr(self, ts_ms: int, value: float) -> VitalSample:
        return VitalSample(
            type=VitalType.heart_rate, ts_ms=ts_ms, value=round(value, 1),
            unit="count/min", source="simulated_watch",
        )

    def _hrv(self, ts_ms: int, elevated: bool) -> VitalSample:
        base = 58.0 + self.rng.uniform(-4.0, 4.0) - (22.0 if elevated else 0.0)
        return VitalSample(
            type=VitalType.hrv_sdnn, ts_ms=ts_ms, value=round(max(base, 12.0), 1),
            unit="ms", source="simulated_watch",
        )

    def _resp(self, ts_ms: int, elevated: bool) -> VitalSample:
        base = 14.0 + self.rng.uniform(-0.5, 0.5) + (3.0 if elevated else 0.0)
        return VitalSample(
            type=VitalType.respiratory_rate, ts_ms=ts_ms, value=round(base, 1),
            unit="count/min", source="simulated_watch",
        )
