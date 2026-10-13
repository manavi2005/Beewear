"""End-to-end pipeline tests on synthetic and replay data (no network, no keys)."""

from __future__ import annotations

import json
import tempfile

from attune.config import Settings
from attune.models import VitalSample, VitalType
from attune.pipeline import Pipeline, default_window
from attune.store import Store


def _settings(**overrides) -> Settings:
    base = dict(
        conversation_source="synthetic", vitals_source="synthetic", coach_backend="template"
    )
    base.update(overrides)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        base.setdefault("db_path", f.name)
    return Settings(**base)


def test_synthetic_pipeline_finds_the_hard_moment():
    result = Pipeline(_settings()).run(*default_window(60))
    assert result.n_utterances > 0
    assert result.n_vitals > 0
    assert result.salient_moments, "expected at least one salient moment"

    # The top moment should be the sharding/joins one, carrying a vitals delta.
    top = result.salient_moments[0]
    assert "shard" in top.utterance.text.lower() or "join" in top.utterance.text.lower()
    assert VitalType.heart_rate in top.vitals_context
    assert top.vitals_context[VitalType.heart_rate].direction == "elevated"


def test_every_recommendation_is_guardrail_compliant():
    result = Pipeline(_settings()).run(*default_window(60))
    assert result.recommendations
    banned = ("anxious", "nervous", "stressed", "confused you", "you were confused")
    for rec in result.recommendations:
        low = rec.body.lower()
        assert not any(b in low for b in banned)
        assert rec.generated_by == "template"


def test_self_report_ranks_top_and_is_coached():
    """The authoritative self-report should attach, rank the moment top, and be coached."""
    result = Pipeline(_settings()).run(*default_window(60))
    assert result.n_checkins >= 1
    top = result.salient_moments[0]
    assert top.checkin is not None and top.checkin.value == 4.0
    assert any(s.kind == "self_report" and s.weight == 1.0 for s in top.signals)
    assert any("rated" in r.body.lower() for r in result.recommendations)


def test_neurolearn_vertical_adds_study_signals_and_profile():
    result = Pipeline(_settings(vertical="neurolearn")).run(*default_window(60))
    kinds = {s.kind for m in result.salient_moments for s in m.signals}
    assert "study_objective" in kinds
    assert "concept_link" in kinds
    assert any(
        "review block" in r.body.lower() or "from memory" in r.body.lower()
        for r in result.recommendations
    )


def test_generic_vertical_keeps_vertical_detectors_out():
    result = Pipeline(_settings(vertical="generic")).run(*default_window(60))
    kinds = {s.kind for m in result.salient_moments for s in m.signals}
    assert "study_objective" not in kinds
    assert "concept_link" not in kinds


def test_salience_is_serialized_for_the_dashboard():
    """The dashboard ranks moments by salience, so it must be in the JSON (regression)."""
    result = Pipeline(_settings()).run(*default_window(60))
    dumped = json.loads(result.model_dump_json())
    assert dumped["salient_moments"], "expected salient moments"
    assert "salience" in dumped["salient_moments"][0]
    assert dumped["salient_moments"][0]["salience"] > 0


def test_vitals_ingestion_is_idempotent():
    """Re-adding the same samples must not accumulate duplicates (Live mode / re-runs)."""
    settings = _settings()
    store = Store(settings.db_path)
    start, end = default_window(60)
    batch = [
        VitalSample(type=VitalType.heart_rate, ts_ms=start + i * 1000, value=70 + i,
                    unit="count/min", source="apple_watch")
        for i in range(10)
    ]
    assert store.add_vitals(batch) == 10
    assert store.add_vitals(batch) == 0  # all duplicates ignored
    assert len(store.get_vitals(start, end)) == 10


def test_replay_source_runs():
    result = Pipeline(_settings(conversation_source="replay")).run(*default_window(60))
    assert result.n_utterances > 0


def test_api_vitals_source_reads_from_store():
    """When vitals_source='api', the pipeline should read vitals the app pushed to the store."""
    settings = _settings(vitals_source="api")
    store = Store(settings.db_path)
    start, end = default_window(60)
    # Simulate the companion app pushing a sample mid-window.
    store.add_vitals(
        [
            VitalSample(
                type=VitalType.heart_rate,
                ts_ms=(start + end) // 2,
                value=80,
                unit="count/min",
                source="apple_watch",
            )
        ]
    )
    result = Pipeline(settings, store=store).run(start, end)
    assert result.n_vitals == 1
