# Ethics & Guardrails

These are not aspirational notes — they are **product constraints enforced in code**
(`attune/coach/guardrails.py`, `attune/align/baseline.py`). This file explains *why* they
exist so nobody "optimizes" them away during a late-night hackathon push.

## The core scientific claim we refuse to make

An Apple Watch measures **physiological signals** (heart rate, HRV, respiratory rate, sleep,
movement). It does **not** read the nervous system, emotions, or thoughts. HRV in particular
is affected by exercise, sleep, caffeine, illness, posture, and measurement conditions, and
**HRV alone is not a reliable quantifier of psychological stress**.

Therefore Attune **never** says things like:
- "You were anxious." / "You were confused." / "You were stressed."
- "Your heart rate shows you didn't understand this."
- Any claim that maps a physiological value to an emotional or cognitive state.

Instead it says things like:
- "Your heart rate was **elevated relative to this session's earlier readings** while
  discussing database sharding. That alone doesn't establish how you felt — want to rehearse
  that explanation and compare your self-reported confidence next time?"

The difference between those two sentences is the entire ethical posture of the product.

## Enforced rules

| # | Rule | Enforced where |
|---|---|---|
| 1 | **Baseline-relative only.** Signals are computed vs. the user's *own* recent baseline, never population thresholds. | `align/baseline.py`, `detect/rules.py` |
| 2 | **No emotion/cognition inference.** The coach may describe signals and suggest actions, but must not assert internal states. | `coach/guardrails.py` (system prompt + post-hoc `scrub()`) |
| 3 | **Correlation ≠ causation, stated.** When vitals and a conversation moment co-occur, outputs explicitly note co-occurrence is not causation. | `coach/guardrails.py` |
| 4 | **Self-report is first-class.** The user's own `CheckIn` ("that felt hard: 4/5") outranks any inferred signal. | `models.CheckIn`, aligner weighting |
| 5 | **Private coaching, not evaluation.** Framing is always the user coaching themselves. Never an employer's or third party's assessment. | `coach/guardrails.py`, product copy |
| 6 | **Opt-in and local-first.** Data stays in a local SQLite file; nothing is uploaded except the user's own calls to their own Bee account / their own Anthropic key. | `store.py`, `config.py` |
| 7 | **Suggestions, not commands.** Output is phrased as questions/options ("want to…?"), never directives about health. | `coach/guardrails.py` |
| 8 | **No medical/diagnostic language.** "Flag unusual trends without diagnosing causes." No thresholds presented as clinical. | `coach/guardrails.py` |

## `scrub()` — the post-hoc safety net

Even with a careful system prompt, an LLM can drift. `coach/guardrails.scrub()` runs on
every generated recommendation and flags/rewrites banned patterns (emotional verdicts,
diagnostic phrasing, absolute causal claims). If a recommendation can't be made compliant, it
is dropped rather than shown. This is why the coach is allowed to produce *fewer* outputs than
moments detected.

## Privacy posture

- **Local-first:** the pipeline reads your Bee data via *your* local proxy and stores derived
  records in a local SQLite file under your control. Delete the file to delete the data.
- **No third-party sharing:** vitals from the companion app are sent only to *your* core's
  `/ingest` endpoint (default `127.0.0.1`), never to us or anyone else.
- **Minimal retention:** only the fields needed for alignment and coaching are stored; raw
  Health exports are read and discarded, not re-hosted.
- **Keys never in git:** secrets live in `.env` (gitignored); see `core/.env.example`.

## If you demo this

Say out loud, once, at the start: *"This is private self-coaching. It describes signals
relative to my own baseline and never diagnoses or reads emotions."* It's honest, it
pre-empts the obvious judge question, and it's the actual behavior of the code.
