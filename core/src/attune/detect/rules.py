"""Generic, concept-agnostic detectors (ADR-005).

Design notes:
- Linguistic detectors fire only on the user's **own** utterances (``speaker == "me"``).
  They read the user's own words — a form of self-report — never an inference about an
  internal state from physiology (ETHICS rules 2 & 4).
- ``VitalsDeltaDetector`` speaks strictly in baseline-relative terms (ETHICS rule 1) and
  never attaches a feeling to the number.
"""

from __future__ import annotations

import re
from collections import Counter

from attune.detect.base import Detector
from attune.models import Moment, Signal

_ME = {"me", "user", "self"}


def _is_me(moment: Moment) -> bool:
    return moment.utterance.speaker.lower() in _ME or moment.utterance.speaker == ""


class HesitationDetector(Detector):
    """Filler words / explicit uncertainty markers in the user's speech."""

    name = "hesitation"
    _pattern = re.compile(
        r"\b(um+|uh+|hmm+|erm?|i'?m not sure|not sure|i guess|kind of|sort of|maybe)\b",
        re.IGNORECASE,
    )

    def detect(self, moment: Moment, all_moments: list[Moment]) -> list[Signal]:
        if not _is_me(moment):
            return []
        hits = self._pattern.findall(moment.utterance.text)
        if not hits:
            return []
        weight = min(1.0, 0.35 + 0.2 * len(hits))
        return [
            Signal(
                kind="hesitation",
                detector=self.name,
                weight=weight,
                evidence=f"markers: {', '.join(sorted({h.lower() for h in hits}))}",
            )
        ]


class SelfCorrectionDetector(Detector):
    """The user revises an answer mid-stream — a strong 'worth revisiting' cue."""

    name = "self_correction"
    _pattern = re.compile(
        r"(wait,?\s*no|actually,?|let me re-?think|i mean,?|scratch that|correction"
        r"|on second thought)",
        re.IGNORECASE,
    )

    def detect(self, moment: Moment, all_moments: list[Moment]) -> list[Signal]:
        if not _is_me(moment):
            return []
        m = self._pattern.search(moment.utterance.text)
        if not m:
            return []
        return [
            Signal(
                kind="self_correction",
                detector=self.name,
                weight=0.7,
                evidence=f'phrase: "{m.group(0).strip()}"',
            )
        ]


class UncertaintyDetector(Detector):
    """The user explicitly states they don't understand / want clarification."""

    name = "uncertainty"
    _pattern = re.compile(
        r"(i don'?t (fully |really )?understand|i don'?t (get|follow)|i'?m lost|"
        r"wait,?\s*what|confused about|need to review|want to review)",
        re.IGNORECASE,
    )

    def detect(self, moment: Moment, all_moments: list[Moment]) -> list[Signal]:
        if not _is_me(moment):
            return []
        m = self._pattern.search(moment.utterance.text)
        if not m:
            return []
        return [
            Signal(
                kind="uncertainty",
                detector=self.name,
                weight=0.85,
                evidence=f'said: "{m.group(0).strip()}"',
            )
        ]


class RepeatedTopicDetector(Detector):
    """Content words the user returns to across moments — likely a sticking point."""

    name = "repeated_topic"
    _stop = {
        "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with", "we",
        "i", "you", "it", "that", "this", "would", "could", "how", "what", "is", "are",
        "be", "do", "so", "if", "about", "here", "there", "my", "me", "let", "like",
        "actually", "think", "not", "sure", "yeah", "okay", "them", "they", "can", "re",
    }
    _word = re.compile(r"[a-zA-Z][a-zA-Z\-]{3,}")

    def _terms(self, text: str) -> set[str]:
        return {w.lower() for w in self._word.findall(text) if w.lower() not in self._stop}

    def detect(self, moment: Moment, all_moments: list[Moment]) -> list[Signal]:
        if not _is_me(moment):
            return []
        # Count how many distinct "me" moments each term appears in.
        doc_freq: Counter[str] = Counter()
        for m in all_moments:
            if _is_me(m):
                doc_freq.update(self._terms(m.utterance.text))
        repeated = [t for t in self._terms(moment.utterance.text) if doc_freq[t] >= 2]
        if not repeated:
            return []
        return [
            Signal(
                kind="repeated_topic",
                detector=self.name,
                weight=min(1.0, 0.3 + 0.2 * len(repeated)),
                evidence=f"recurring: {', '.join(sorted(repeated))}",
            )
        ]


class CheckInDetector(Detector):
    """The user's own self-report — the single most authoritative signal (ETHICS rule 4).

    A reported difficulty outranks anything inferred from physiology, so this emits the
    maximum weight. It reads only what the person stated, never an inference.
    """

    name = "self_report"

    def detect(self, moment: Moment, all_moments: list[Moment]) -> list[Signal]:
        c = moment.checkin
        if c is None:
            return []
        parts = []
        if c.value is not None:
            parts.append(f"rated {c.value:g}")
        if c.label:
            parts.append(f'"{c.label}"')
        detail = ", ".join(parts) if parts else "self-report recorded"
        return [
            Signal(
                kind="self_report",
                detector=self.name,
                weight=1.0,
                evidence=f"you {detail}" + (f' ({c.prompt})' if c.prompt else ""),
            )
        ]


class VitalsDeltaDetector(Detector):
    """A physiological reading unusual *vs. the user's own baseline* at this moment.

    Deliberately valence-free: it reports direction + distance, never a feeling (ETHICS 1 & 2).
    """

    name = "vitals_delta"

    def detect(self, moment: Moment, all_moments: list[Moment]) -> list[Signal]:
        signals: list[Signal] = []
        for vtype, delta in moment.vitals_context.items():
            if delta.direction == "typical":
                continue
            weight = min(1.0, 0.3 + 0.25 * abs(delta.z or 0.0))
            signals.append(
                Signal(
                    kind="vitals_delta",
                    detector=self.name,
                    weight=weight,
                    evidence=(
                        f"{vtype.value} {delta.direction} vs. your baseline "
                        f"({delta.value} vs ~{delta.baseline}, z={delta.z})"
                    ),
                )
            )
        return signals


# The default detector stack used by the pipeline (ADR-005). CheckInDetector is first because
# self-report is authoritative (ETHICS rule 4). Append vertical-specific detectors here or via
# config to specialize later.
DEFAULT_DETECTORS: list[Detector] = [
    CheckInDetector(),
    HesitationDetector(),
    SelfCorrectionDetector(),
    UncertaintyDetector(),
    RepeatedTopicDetector(),
    VitalsDeltaDetector(),
]
