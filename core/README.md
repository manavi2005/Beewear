# Attune — core

The NeuroLearn demo layer on top of Attune: ingest Bee learning-session context + Apple Watch
physiology, align them in time, surface notable moments, and generate hedged,
baseline-relative study coaching. Set `ATTUNE_VERTICAL=generic` to run the reusable base
without NeuroLearn-specific detectors.

> Full design in [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md); every decision in
> [`../docs/DECISIONS.md`](../docs/DECISIONS.md); guardrails in
> [`../docs/ETHICS.md`](../docs/ETHICS.md).

## Quickstart (free, no hardware, no keys)

```bash
cd core
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # defaults: synthetic data + free template coach
attune run                      # end-to-end pipeline on generated data
```

You should see a conversation, the salient moments it detected (hesitation, self-correction,
stated uncertainty, a repeated topic, NeuroLearn study signals, a baseline-relative vitals
change), and a short list of recommendations — all produced with **zero cost** (ADR-017).

## Common commands

```bash
attune run                      # synthetic demo (default)
attune run --source replay      # replay a recorded Bee conversation fixture
attune run --json               # full machine-readable result
attune version                  # show active config + whether the coach is free/paid
attune serve                    # start the ingestion+run API (for the companion app)
pytest                          # run the test suite
```

## Using real data

| Want | Set in `.env` | Prereq |
|---|---|---|
| Real Bee conversations | `ATTUNE_CONVERSATION_SOURCE=bee` | `npm i -g @beeai/cli && bee login && bee proxy` |
| Live Watch vitals (companion app) | `ATTUNE_VITALS_SOURCE=api` + run `attune serve` | build `../companion` in Xcode |
| Batch Watch vitals (no app) | `ATTUNE_VITALS_SOURCE=health_export` + `ATTUNE_HEALTH_EXPORT_PATH=...` | export from Health app |
| Nicer phrasing, still free | `ATTUNE_COACH_BACKEND=ollama` | `ollama pull llama3.2` |
| Claude-quality phrasing (PAID) | `ATTUNE_COACH_BACKEND=anthropic` + `ANTHROPIC_API_KEY=...` | API key / credits |

## Layout

```
src/attune/
  config.py        settings (env-driven)
  models.py        canonical domain model
  sources/         Bee + vitals adapters (+ replay/synthetic twins)
  align/           baseline + timestamp aligner
  detect/          pluggable moment detectors
  coach/           guardrails + template/ollama/anthropic backends
  store.py         SQLite persistence
  pipeline.py      orchestration
  api.py           FastAPI service
  cli.py           `attune` command
fixtures/          sample Bee conversation + Apple Health export
tests/             pytest suite
```
