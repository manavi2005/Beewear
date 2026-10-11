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


class StudyObjectiveDetector(Detector):
    """NeuroLearn: the user names something they want to study, review, or practice."""

    name = "neurolearn_study_objective"
    _pattern = re.compile(
        r"\b("
        r"want to review|need to review|want to study|need to study|"
        r"review before|practice|rehearse|learn more about|next time"
        r")\b",
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
                kind="study_objective",
                detector=self.name,
                weight=0.8,
                evidence=f'study objective: "{m.group(0).strip()}"',
            )
        ]


class ConceptLinkDetector(Detector):
    """NeuroLearn: multiple technical concepts named together can become a review map."""

    name = "neurolearn_concept_link"
    _concepts = {
        "base62": re.compile(r"\bbase\s*62|base62\b", re.IGNORECASE),
        "cache": re.compile(r"\bcach(?:e|ing)\b", re.IGNORECASE),
        "collisions": re.compile(r"\bcollid(?:e|es|ing)|collisions?\b", re.IGNORECASE),
        "consistent hashing": re.compile(r"\bconsistent hashing\b", re.IGNORECASE),
        "cross-shard joins": re.compile(r"\bcross[-\s]?shard joins?\b", re.IGNORECASE),
        "database": re.compile(r"\bdatabases?\b", re.IGNORECASE),
        "hashing": re.compile(r"\bhash(?:ing)?\b", re.IGNORECASE),
        "sharding": re.compile(r"\bshard(?:ing|s|ed)?\b", re.IGNORECASE),
        "system design": re.compile(r"\bsystem design\b", re.IGNORECASE),
    }

    def detect(self, moment: Moment, all_moments: list[Moment]) -> list[Signal]:
        if not _is_me(moment):
            return []
        found = [
            name
            for name, pattern in self._concepts.items()
            if pattern.search(moment.utterance.text)
        ]
        if len(found) < 2:
            return []
        return [
            Signal(
                kind="concept_link",
                detector=self.name,
                weight=min(1.0, 0.45 + 0.15 * len(found)),
                evidence=f"concept links: {', '.join(found)}",
            )
        ]


# The reusable detector stack used by the generic base layer (ADR-005). CheckInDetector is
# first because self-report is authoritative (ETHICS rule 4).
GENERIC_DETECTORS: list[Detector] = [
    CheckInDetector(),
    HesitationDetector(),
    SelfCorrectionDetector(),
    UncertaintyDetector(),
    RepeatedTopicDetector(),
    VitalsDeltaDetector(),
]

# NeuroLearn specializes Attune for study/interview-prep learning sessions (ADR-022).
NEUROLEARN_DETECTORS: list[Detector] = [
    CheckInDetector(),
    StudyObjectiveDetector(),
    ConceptLinkDetector(),
    HesitationDetector(),
    SelfCorrectionDetector(),
    UncertaintyDetector(),
    RepeatedTopicDetector(),
    VitalsDeltaDetector(),
]

# Backwards-compatible default for code that imports the detector stack directly.
DEFAULT_DETECTORS: list[Detector] = NEUROLEARN_DETECTORS


def build_detectors(vertical: str) -> list[Detector]:
    """Build a fresh detector stack for the configured product vertical."""
    if vertical == "generic":
        return [type(d)() for d in GENERIC_DETECTORS]
    return [type(d)() for d in NEUROLEARN_DETECTORS]
