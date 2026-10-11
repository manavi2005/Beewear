# Architecture

> Working codename: **Attune** (ADR-016). Concept-agnostic base layer for an adaptive AI
> coach that combines **what you discussed** (Bee) with **how your body responded** (Apple
> Watch), aligned in time.

## One-paragraph summary

Two independent pipelines — conversation context from **Bee** and physiological signals from
an **Apple Watch** — are each translated into one **canonical domain model** at their adapter
boundary, persisted to a local **SQLite** store keyed by UTC-epoch-millisecond timestamps,
then **aligned in time** to produce *moments*. Pluggable **detectors** annotate moments
(linguistic hesitation, vitals deltas vs. a personal baseline), and a guardrailed **coach**
turns notable moments into hedged, personalized recommendations. Everything is driven by a
small **FastAPI** service and a **CLI**, and every external source has a **replay/synthetic
twin** so the whole thing runs with zero hardware.

## Data flow

```
          CONVERSATION PIPELINE                        PHYSIOLOGY PIPELINE
          (what you discussed)                         (how your body responded)

  Bee app / Apple Watch (Bee software)          Apple Watch  ──HealthKit──┐
        │ records speech                                                   │
        ▼                                          ┌────────────────┬──────┴───────┐
  Bee cloud                                        ▼                ▼              ▼
        │                                   companion app     Health export   (no app)
  bee login + bee proxy                     (watchOS/iOS)      export.xml      synthetic
  127.0.0.1:8787  /v1/*                      POST /ingest       (batch)        generator
        │                                         │                │              │
        ▼                                         ▼                ▼              ▼
  ┌───────────────┐                        ┌──────────────────────────────────────┐
  │ BeeProxySource│                        │            VitalsSource(s)            │
  │ BeeReplaySource│                       │ Companion→API / HealthExport / Synthetic│
  └───────┬───────┘                        └───────────────────┬───────────────────┘
          │  canonical Utterance/Conversation                  │ canonical VitalSample
          └──────────────────────────┬─────────────────────────┘
                                      ▼
                             ┌─────────────────┐
                             │   SQLite store  │  (ts_ms-keyed, canonical JSON)
                             └────────┬────────┘
                                      ▼
                             ┌─────────────────┐
                             │   Aligner       │  join utterances ↔ vitals in a window,
                             │  + Baseline     │  compute deltas vs. PERSONAL baseline
                             └────────┬────────┘
                                      ▼  Moments (utterance + vitals context)
                             ┌─────────────────┐
                             │  Detectors      │  pluggable: hesitation, self-correction,
                             │  (Strategy)     │  repeated-topic, vitals-delta
                             └────────┬────────┘
                                      ▼  Signals attached to Moments
                             ┌─────────────────┐
                             │  Coach          │  Claude + GUARDRAILS (baseline-relative,
                             │  (guardrailed)  │  no emotion/diagnosis) → Recommendations
                             └────────┬────────┘
                                      ▼
                      FastAPI  /run  ·  /sessions   +   CLI  `attune run`
```

## Modules (Python package `attune`, under `core/src/attune/`)

| Module | Responsibility | Key types / entry points |
|---|---|---|
| `config.py` | 12-factor settings from env/`.env` (ADR-012) | `Settings`, `get_settings()` |
| `models.py` | Canonical, source-agnostic domain model (ADR-007) | `Utterance`, `Conversation`, `VitalSample`, `CheckIn`, `Session`, `Moment`, `Signal`, `Recommendation` |
| `sources/base.py` | Abstract source interfaces (Strategy) | `ConversationSource`, `VitalsSource` |
| `sources/bee.py` | Live Bee via local proxy REST+SSE (ADR-003) | `BeeProxySource` |
| `sources/bee_replay.py` | Replay recorded Bee fixtures (ADR-010) | `BeeReplaySource` |
| `sources/health_export.py` | Parse Apple Health `export.xml` (ADR-006) | `HealthExportSource` |
| `sources/synthetic.py` | Deterministic fake data (ADR-010) | `SyntheticVitalsSource`, `SyntheticConversationSource` |
| `store.py` | SQLite persistence, ts-range queries (ADR-013) | `Store` |
| `align/baseline.py` | Personal baseline per vital type (ADR-011) | `Baseline`, `rolling_baseline()` |
| `align/aligner.py` | Join utterances ↔ vitals → `Moment`s (ADR-008) | `Aligner` |
| `detect/base.py` | Detector interface (Strategy) | `Detector` |
| `detect/rules.py` | Generic, concept-agnostic detectors (ADR-005) | `HesitationDetector`, `SelfCorrectionDetector`, `RepeatedTopicDetector`, `VitalsDeltaDetector` |
| `coach/guardrails.py` | Enforced ethical constraints (ADR-011) | `GUARDRAILS`, `scrub()` |
| `coach/coach.py` | Claude-backed recommendations (ADR-014) | `Coach`, `TemplateCoach` |
| `pipeline.py` | Orchestrates source → store → align → detect → coach | `Pipeline` |
| `api.py` | FastAPI ingestion + run service (ADR-009) | `app` |
| `cli.py` | `attune` command-line entry point | `main()` |

## The companion app (`companion/`)

watchOS + iOS app (Swift) that requests HealthKit authorization, reads recent samples
(heart rate, HRV/SDNN, respiratory rate, sleep), maps them to the **same `VitalSample`
JSON schema** the core expects, and `POST`s them to `/ingest/vitals`. It is deliberately
thin: all intelligence lives in the core. See `companion/README.md` for the Xcode setup,
entitlements, and backend URL configuration.

## Design principles

1. **One contract, many sources.** Everything downstream of an adapter sees only canonical
   models. New source = one adapter.
2. **Nothing hard-depends on hardware or network.** Replay/synthetic twins keep the demo
   alive (ADR-010).
3. **Baseline-relative, never diagnostic.** Ethics are enforced in code, not just docs
   (ADR-011, `docs/ETHICS.md`).
4. **Deterministic core, probabilistic edge.** The pipeline is deterministic and testable;
   only the coach calls an LLM, and it degrades to a template coach without a key.
5. **Time is the join key.** All timestamps are UTC epoch ms (ADR-008).

## Running it (preview)

```bash
cd core
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # defaults to the synthetic source — runs with no hardware
attune run --source synthetic   # end-to-end pipeline on generated data
uvicorn attune.api:app --reload # ingestion + run service for the companion app
```

See the top-level `README.md` for the full quickstart including live Bee + the companion app.
