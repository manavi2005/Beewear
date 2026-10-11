"""Synthetic sources (ADR-010): deterministic fake data so the pipeline runs with zero
hardware, logins, or network. This is what a fresh clone uses by default.

The script is intentionally crafted to exercise every generic detector:
- hesitation markers ("um", "hmm", "I'm not sure")
- a self-correction ("wait, no ... let me re-think")
- an "I don't understand" moment
- a repeated topic ("shard"/"joins")
- a vitals elevation (vs. the session's own baseline) around the hard moment

Both sources anchor to the *end* of the requested window, so they always fill whatever
range the caller asks for — the demo can never come back empty because of the clock.
"""

from __future__ import annotations

import random
from collections.abc import Iterable

from attune.models import Conversation, Utterance, VitalSample, VitalType

# ruff: noqa: E501  — the scripted utterances below read better unwrapped (demo data)

# (speaker, offset_seconds_from_session_start, text)
_SCRIPT: list[tuple[str, int, str]] = [
    ("other", 0, "Alright, whenever you're ready — walk me through how you'd design a URL shortener."),
    ("me", 8, "Sure. We'd need a service that takes a long URL and returns a short key."),
    ("me", 22, "We'd store the mapping in a database, and, um, generate a unique key for each URL."),
    ("other", 45, "How would you generate the key?"),
    ("me", 52, "We could hash the URL — wait, no, hashing could collide. Let me re-think that."),
    ("me", 78, "Actually we'd use an auto-incrementing ID and base62-encode it."),
    ("other", 110, "Good. What happens when traffic grows?"),
    ("me", 120, "We'd add a cache in front of the database for the hot keys."),
    # ── the hard moment, ~18 min in (mirrors the PDF's minute-18 sharding example) ──
    ("other", 1070, "Let's talk scale. How would you shard the database?"),
    ("me", 1082, "Hmm. I think sharding would work here, but I'm not sure how to handle joins across shards."),
    ("me", 1108, "I don't fully understand how cross-shard joins stay consistent, honestly."),
    ("other", 1140, "That's a genuinely hard part — we can come back to it."),
    ("me", 1152, "Yeah. I'd want to review consistent hashing and cross-shard joins before next time."),
]

_SESSION_SECONDS = 20 * 60  # 20-minute session
_HARD_MOMENT_S = 1082  # offset of the elevated-vitals centre


class SyntheticConversationSource:
    """Generates one scripted technical conversation anchored to the window end."""

    name = "synthetic"

    def fetch(self, start_ms: int, end_ms: int) -> Iterable[Conversation]:
        session_start = end_ms - _SESSION_SECONDS * 1000
        conv_id = "synthetic-conv-1"
        utterances: list[Utterance] = []
        for i, (speaker, offset_s, text) in enumerate(_SCRIPT):
            ts = session_start + offset_s * 1000
            if ts < start_ms or ts > end_ms:
                continue
            utterances.append(
                Utterance(
                    id=f"{conv_id}-u{i}",
                    ts_ms=ts,
                    speaker=speaker,
                    text=text,
                    conversation_id=conv_id,
                )
            )
        if not utterances:
            return []
        return [
            Conversation(
                id=conv_id,
                start_ms=session_start,
                end_ms=end_ms,
                summary="Mock system-design discussion: URL shortener, caching, sharding.",
                utterances=utterances,
            )
        ]


class SyntheticVitalsSource:
    """Generates HR / HRV / respiratory samples with an elevation around the hard moment.

    Values rise *relative to the session's own baseline* — exactly what the baseline-relative
    analysis (ADR-011) is designed to read. Nothing here claims an emotional state.
    """

    name = "synthetic"

    def fetch(self, start_ms: int, end_ms: int) -> Iterable[VitalSample]:
        rng = random.Random(42)
        session_start = end_ms - _SESSION_SECONDS * 1000
        samples: list[VitalSample] = []

        def arousal(offset_s: int) -> float:
            """0..1 bump centred on the hard moment, ~2-minute width."""
            dt = abs(offset_s - _HARD_MOMENT_S)
            return max(0.0, 1.0 - dt / 120.0)

        # Heart rate every 5s (Apple Watch Series 12 passive cadence).
        for offset_s in range(0, _SESSION_SECONDS + 1, 5):
            ts = session_start + offset_s * 1000
            if ts < start_ms or ts > end_ms:
                continue
            base = 70 + rng.uniform(-2.5, 2.5)
            value = base + 32 * arousal(offset_s)  # up to ~102 bpm at the peak
            samples.append(
                VitalSample(
                    type=VitalType.heart_rate,
                    ts_ms=ts,
                    value=round(value, 1),
                    unit="count/min",
                    source="synthetic",
                )
            )

        # HRV (SDNN) every 60s — drops as heart rate rises.
        for offset_s in range(0, _SESSION_SECONDS + 1, 60):
            ts = session_start + offset_s * 1000
            if ts < start_ms or ts > end_ms:
                continue
            base = 58 + rng.uniform(-4, 4)
            value = base - 24 * arousal(offset_s)  # down to ~34 ms at the peak
            samples.append(
                VitalSample(
                    type=VitalType.hrv_sdnn,
                    ts_ms=ts,
                    value=round(max(value, 10.0), 1),
                    unit="ms",
                    source="synthetic",
                )
            )

        # Respiratory rate every 60s — slight rise.
        for offset_s in range(0, _SESSION_SECONDS + 1, 60):
            ts = session_start + offset_s * 1000
            if ts < start_ms or ts > end_ms:
                continue
            base = 14 + rng.uniform(-0.6, 0.6)
            value = base + 3 * arousal(offset_s)
            samples.append(
                VitalSample(
                    type=VitalType.respiratory_rate,
                    ts_ms=ts,
                    value=round(value, 1),
                    unit="count/min",
                    source="synthetic",
                )
            )

        return samples
