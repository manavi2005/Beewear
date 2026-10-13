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
attune serve                    # start the ingestion+run API + live dashboard
attune doctor                   # readiness checklist for testing on your Apple Watch
attune simulate-watch           # stream fake Watch vitals to a running server (no Watch needed)
pytest                          # run the test suite
```

## Test the whole loop without the Watch (or before the app is built)

```bash
attune serve --lan              # terminal 1 — binds LAN, prints the URL for the dashboard/app
attune simulate-watch           # terminal 2 — streams fake Apple Watch vitals into it
# open http://127.0.0.1:8000/  → click "● Live" and watch the heart-rate chart update
```

The dashboard (served at `/`) shows a live BPM tile, a heart-rate chart with the salient
moments marked, the ranked recommendations, and 1–5 **check-in buttons** that send a
self-report (the authoritative signal). **Live** mode is push-based: it subscribes to a
Server-Sent Events stream (`GET /events`), so the BPM and chart update the instant a sample is
ingested — no polling (ADR-025). `attune simulate-watch --backfill 15` seeds 15 minutes of
history in one shot instead of streaming.

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
  store.py         SQLite persistence (idempotent vitals ingestion)
  pipeline.py      orchestration
  api.py           FastAPI service + live dashboard + SSE (/events)
  events.py        in-process pub/sub broker for Server-Sent Events
  simulate.py      software Apple Watch (for simulate-watch)
  netutil.py       LAN-IP discovery (for doctor / serve --lan)
  cli.py           `attune` command
fixtures/          sample Bee conversation + Apple Health export
tests/             pytest suite
```
