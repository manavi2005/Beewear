# Canonical Data Model

The single source of truth is `core/src/attune/models.py` (Pydantic v2). This document is a
human-readable companion. Every adapter translates its source's native shape into these types
at the boundary (ADR-007); nothing downstream sees raw Bee/HealthKit JSON.

**Golden rule:** all timestamps are `ts_ms` — **UTC epoch milliseconds, `int`** (ADR-008).

## Entities

### `Utterance` — one spoken line (from Bee)
| field | type | notes |
|---|---|---|
| `id` | `str` | stable id from the source |
| `ts_ms` | `int` | start time, UTC epoch ms |
| `speaker` | `str` | `"me"` / `"other"` / raw label |
| `text` | `str` | transcribed text |
| `conversation_id` | `str \| None` | parent conversation |

### `Conversation` — a grouped set of utterances (from Bee)
| field | type | notes |
|---|---|---|
| `id` | `str` | source id |
| `start_ms` / `end_ms` | `int` | bounds, UTC epoch ms |
| `summary` | `str \| None` | Bee short summary |
| `utterances` | `list[Utterance]` | may be empty if not expanded |

### `VitalSample` — one physiological reading (from Apple Watch / HealthKit)
This is **also the `POST /ingest/vitals` request schema** (ADR-009).
| field | type | notes |
|---|---|---|
| `type` | `VitalType` | enum: `heart_rate`, `hrv_sdnn`, `respiratory_rate`, `wrist_temperature`, `sleep`, `movement` |
| `ts_ms` | `int` | sample start, UTC epoch ms |
| `end_ms` | `int \| None` | for interval samples (sleep) |
| `value` | `float` | numeric value |
| `unit` | `str` | e.g. `"count/min"`, `"ms"`, `"°C"` |
| `source` | `str` | `"apple_watch"`, `"health_export"`, `"synthetic"` |

### `CheckIn` — user self-report (first-class; ADR / ETHICS rule 4)
| field | type | notes |
|---|---|---|
| `ts_ms` | `int` | when reported |
| `prompt` | `str` | what was asked ("How hard did that feel?") |
| `value` | `float \| None` | e.g. 1–5 |
| `label` | `str \| None` | free-text / category |

### `Session` — a bounded analysis window
| field | type | notes |
|---|---|---|
| `id` | `str` | generated |
| `start_ms` / `end_ms` | `int` | window bounds |
| `label` | `str \| None` | e.g. "study block", provided by caller (not inferred) |

### `Moment` — an utterance plus its aligned vitals context (produced by the Aligner)
| field | type | notes |
|---|---|---|
| `ts_ms` | `int` | anchor time (the utterance) |
| `utterance` | `Utterance` | the anchor |
| `vitals_window` | `list[VitalSample]` | samples within the alignment window |
| `vitals_context` | `dict[VitalType, VitalDelta]` | per-type delta vs. baseline |
| `signals` | `list[Signal]` | attached by detectors |

### `VitalDelta` — a baseline-relative description (ADR-011)
| field | type | notes |
|---|---|---|
| `type` | `VitalType` | which vital |
| `value` | `float` | the window's representative value |
| `baseline` | `float` | personal baseline |
| `direction` | `"elevated" \| "lowered" \| "typical"` | **relative wording only** |
| `z` | `float \| None` | optional standardized distance from baseline |

> Note there is **no** `emotion`, `stress`, or `confused` field anywhere. That absence is a
> deliberate, enforced design choice (see `docs/ETHICS.md`).

### `Signal` — a detector's annotation on a moment
| field | type | notes |
|---|---|---|
| `kind` | `str` | e.g. `"hesitation"`, `"self_correction"`, `"repeated_topic"`, `"vitals_delta"` |
| `detector` | `str` | which detector produced it |
| `weight` | `float` | 0–1 salience |
| `evidence` | `str` | human-readable justification (quote/marker) |

### `Recommendation` — coach output
| field | type | notes |
|---|---|---|
| `moment_ts_ms` | `int` | which moment it responds to |
| `title` | `str` | short label |
| `body` | `str` | hedged suggestion (guardrail-compliant) |
| `basis` | `list[str]` | the signals/evidence it drew on |
| `generated_by` | `"claude" \| "template"` | provenance |

## Source → canonical mapping (cheat sheet)

| Canonical | Bee (`/v1/*`) | Apple Health (`export.xml`) |
|---|---|---|
| `Utterance` | transcript entries of `/v1/conversations/:id` | — |
| `Conversation` | `/v1/conversations` | — |
| `VitalSample(heart_rate)` | — | `Record type="HKQuantityTypeIdentifierHeartRate"` |
| `VitalSample(hrv_sdnn)` | — | `...HeartRateVariabilitySDNN` (ms) |
| `VitalSample(respiratory_rate)` | — | `...RespiratoryRate` |
| `VitalSample(wrist_temperature)` | — | `...AppleSleepingWristTemperature` |
| `VitalSample(sleep)` | — | `Record type="HKCategoryTypeIdentifierSleepAnalysis"` (interval) |
| `CheckIn` | (optional: a Bee todo/fact convention) | — |
