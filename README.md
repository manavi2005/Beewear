# Attune

[![CI](https://github.com/manavi2005/Beewear/actions/workflows/ci.yml/badge.svg)](https://github.com/manavi2005/Beewear/actions/workflows/ci.yml)

**An adaptive AI coach that understands both the context of your day and your body's response
to it.** Built for the Amazon "Bee (Wearable AI)" hackathon.

Attune combines two streams:

- **What you discussed** — conversation context from **Bee** (via its local CLI/proxy).
- **How your body responded** — physiology from an **Apple Watch** (via HealthKit).

It aligns them in time, surfaces notable *moments* (where you hesitated, corrected yourself,
said you didn't understand, kept returning to a topic — optionally alongside a heart-rate or
HRV change relative to *your own* baseline), and produces short, **hedged, private** coaching.

> The selected hackathon vertical is now **NeuroLearn**: a private study coach that turns
> Bee-captured learning conversations, self-reported difficulty, and baseline-relative Watch
> context into focused review prompts. The reusable Attune base remains available through
> `ATTUNE_VERTICAL=generic`.

## Why this split exists (the one fact that shaped everything)

**Bee provides conversations, not vitals.** We verified this against Bee's official docs and
CLI: Bee exposes conversations, transcripts, facts, todos, summaries — and **no** heart rate,
HRV, or sleep. So physiology comes exclusively from the Apple Watch via HealthKit, and the two
streams are joined by timestamp. This is recorded as [ADR-002](docs/DECISIONS.md) and is the
reason the architecture has two independent pipelines.

## It costs nothing by default

The entire pipeline — ingestion, alignment, detection, and coaching — runs **free**. The coach
defaults to a deterministic, offline `template` backend (no API, no key). A free **local LLM**
option (Ollama) and a paid **Claude** option exist but are strictly opt-in. See
[ADR-017](docs/DECISIONS.md) and [ETHICS](docs/ETHICS.md).

## Repository layout

```
amazon_hackathon/
├── README.md              ← you are here
├── docs/
│   ├── DECISIONS.md        every design decision, ADR-style (start here)
│   ├── ARCHITECTURE.md     components + data-flow diagram
│   ├── DATA_MODEL.md       the canonical schema
│   └── ETHICS.md           enforced guardrails (baseline-relative, no emotion inference)
├── core/                   the Python base layer  (see core/README.md)
│   └── src/attune/         sources · align · detect · coach · pipeline · api · cli
└── companion/              watchOS + iOS app that streams Watch vitals  (see companion/README.md)
```

## 60-second demo (no hardware, no keys, no cost)

```bash
cd core
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
attune run            # full pipeline on synthetic data → moments + recommendations
pytest                # 11 tests, all green
```

## Going live

| Step | What | Where |
|---|---|---|
| Conversations | `npm i -g @beeai/cli && bee login && bee proxy`, then `ATTUNE_CONVERSATION_SOURCE=bee` | [core/README.md](core/README.md) |
| Watch vitals (live) | build the app, run `attune serve`, set `ATTUNE_VITALS_SOURCE=api` | [companion/README.md](companion/README.md) |
| Watch vitals (batch) | export from Health app, set `ATTUNE_VITALS_SOURCE=health_export` | [core/README.md](core/README.md) |
| Nicer phrasing, still free | `ATTUNE_COACH_BACKEND=ollama` | [core/README.md](core/README.md) |

## Design principles

1. **One contract, many sources.** Everything downstream of an adapter sees only the
   canonical model; a new source is one adapter.
2. **Nothing hard-depends on hardware or network** — every source has a replay/synthetic twin.
3. **Baseline-relative, never diagnostic** — the ethics are enforced in code, not just docs.
4. **Deterministic core, optional LLM edge** — the pipeline is testable; only the coach may
   call a model, and it degrades gracefully to free backends.
5. **Time is the join key** — all timestamps are UTC epoch milliseconds.

## Status

- ✅ Core pipeline (sources → store → align → detect → coach) — runs, tested, linted.
- ✅ Bee proxy adapter, Apple Health export parser, synthetic + replay twins.
- ✅ FastAPI ingestion/run service; `attune` CLI.
- ✅ Companion app Swift sources + Xcode guide.
- ✅ Self-report check-ins wired end-to-end as the authoritative signal (ADR-020).
- ✅ GitHub Actions CI: ruff + pytest + CLI smoke test on Python 3.10/3.11/3.12 (ADR-021).
- ✅ NeuroLearn vertical selected with study-objective/concept-link detectors + coach profile (ADR-022).
- ✅ Watch-test tooling: `simulate-watch`, `doctor`, `serve --lan` — exercise the full loop with no hardware (ADR-023).
- ✅ Live dashboard: heart-rate chart with moment markers, BPM tile, one-tap check-ins, Live mode (ADR-024).
- ⏳ Build `companion/` in Xcode and stream from a real Apple Watch (see companion/README.md).
