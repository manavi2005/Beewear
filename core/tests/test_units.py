"""Unit tests for the deterministic pieces: models, baseline, detectors, guardrails, parsing."""

from __future__ import annotations

from attune.align.baseline import Baseline
from attune.coach.guardrails import is_compliant, scrub
from attune.detect.rules import (
    HesitationDetector,
    SelfCorrectionDetector,
    UncertaintyDetector,
    VitalsDeltaDetector,
)
from attune.models import Moment, Utterance, VitalSample, VitalType
from attune.sources.health_export import HealthExportSource


def _utt(text: str, ts_ms: int = 0, speaker: str = "me") -> Utterance:
    return Utterance(id="u", ts_ms=ts_ms, speaker=speaker, text=text)


def test_timestamps_are_int_ms():
    s = VitalSample(type=VitalType.heart_rate, ts_ms=1_700_000_000_000, value=70, unit="count/min")
    assert isinstance(s.ts_ms, int)


def test_baseline_direction_is_relative():
    # Steady ~70 then a spike to 100 → the spike reads "elevated" vs the personal baseline.
    samples = [
        VitalSample(type=VitalType.heart_rate, ts_ms=i * 1000, value=70.0, unit="count/min")
        for i in range(30)
    ]
    b = Baseline(samples)
    delta = b.describe(VitalType.heart_rate, value=100.0, at_ms=30_000, baseline_window_ms=60_000)
    assert delta is not None
    assert delta.direction == "elevated"
    assert delta.baseline < 80


def test_hesitation_only_fires_on_user():
    d = HesitationDetector()
    me = Moment(ts_ms=0, utterance=_utt("um, I'm not sure about this", speaker="me"))
    other = Moment(ts_ms=0, utterance=_utt("um, I'm not sure about this", speaker="other"))
    assert d.detect(me, [me]) != []
    assert d.detect(other, [other]) == []


def test_self_correction_and_uncertainty():
    assert SelfCorrectionDetector().detect(
        Moment(ts_ms=0, utterance=_utt("wait, no, let me re-think that")), []
    )
    assert UncertaintyDetector().detect(
        Moment(ts_ms=0, utterance=_utt("I don't fully understand this")), []
    )


def test_vitals_delta_is_valence_free():
    m = Moment(ts_ms=0, utterance=_utt("x"))
    from attune.models import VitalDelta

    m.vitals_context[VitalType.heart_rate] = VitalDelta(
        type=VitalType.heart_rate, value=100, baseline=70, direction="elevated", z=3.0
    )
    sigs = VitalsDeltaDetector().detect(m, [m])
    assert sigs and "elevated" in sigs[0].evidence
    # No feeling words leak into the evidence.
    assert not any(w in sigs[0].evidence.lower() for w in ("anxious", "nervous", "stressed"))


def test_guardrails_block_emotional_claims():
    assert not is_compliant("You were clearly anxious during that answer.")
    assert is_compliant("Your heart rate was elevated vs. your baseline.")
    assert scrub("You were anxious.") is None  # unsalvageable → dropped
    assert scrub("Your heart rate was elevated vs. your baseline.") is not None


def test_health_export_parser():
    src = HealthExportSource("fixtures/health_export_sample.xml")
    samples = list(src._iter_samples())
    types = {s.type for s in samples}
    assert VitalType.heart_rate in types
    assert VitalType.hrv_sdnn in types
    hr = [s for s in samples if s.type is VitalType.heart_rate]
    assert any(s.value > 90 for s in hr)  # the elevated reading parsed correctly
