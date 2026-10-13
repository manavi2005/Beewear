# Decision Log (ADRs)

This file records **every significant decision** made while building the base layer,
in the order it was made. Each entry follows a lightweight
[ADR](https://adr.github.io/) shape: **Context → Decision → Consequences**.

The goal is that anyone (including future-you at 2am during the hackathon) can read
this top-to-bottom and understand *why* the code looks the way it does — not just
*what* it does.

> Status legend: `accepted` (in effect), `provisional` (easy to revisit),
> `superseded by ADR-NNN` (kept for history).

---

## ADR-000: What we are building

- **Status:** accepted
- **Context:** Amazon "Bee (Wearable AI)" hackathon. The brief: build a project that
  connects to real data recorded through a Bee device **or an Apple Watch running Bee
  software**, using Bee's CLI, MCP, or Agent Skills, and show it doing something useful
  for a person. Priority use cases: education, developer experience, personal productivity.
  Our idea evolved (see `Amazon Hackathon.pdf`) into *"an adaptive AI coach that
  understands both the context of your day (conversations) and your body's response to it
  (physiology)."*
- **Decision:** Build the **base layer** as a **concept-agnostic core**: ingest
  conversation context (Bee) + physiological signals (Apple Watch), align them in time,
  surface notable *moments*, and generate hedged, personalized coaching. Specific verticals
  (Composure AI for interview practice, NeuroLearn for study overload) become thin plugins
  on top later.
- **Consequences:** We optimize for a clean internal contract and extensibility over any
  single demo script. The first demo can be assembled quickly once a vertical is chosen.

---

## ADR-001: Hardware reality — Apple Watch + Bee software, no Bee pendant

- **Status:** accepted
- **Context:** The user has an **Apple Watch**, not the Bee hardware pendant, and will run
  **Bee software** (Bee iOS app + its Apple Watch app) to capture conversations.
- **Decision:** Conversations flow `Bee app/Watch → Bee cloud → local Bee CLI`. Vitals flow
  `Apple Watch → HealthKit → companion app / Health export`. These are **two independent
  pipelines joined by timestamp**, never one device.
- **Consequences:** We must not assume a single data source. The core aligns two streams
  that can arrive at different times and cadences.

---

## ADR-002: Bee exposes conversations, NOT vitals (verified)

- **Status:** accepted
- **Context:** The PDF flagged that Bee's developer interface might not expose vitals. We
  verified against the official docs (docs.bee.computer) and the `bee-cli` reference:
  Bee exposes **conversations, utterances/transcripts, facts, todos, daily summaries,
  journals, locations, insights, photos** — and **no heart rate, HRV, respiratory rate, or
  sleep anywhere**.
- **Decision:** Treat Bee as the **conversation/context source only**. All physiological
  data comes from Apple HealthKit via a separate pipeline.
- **Consequences:** Settles the architecture debate in the PDF. Vitals are an *additional
  input*, not a replacement; the Bee requirement is still satisfied because the experience
  is genuinely powered by Bee's recorded conversation data.

---

## ADR-003: Consume Bee via its local HTTP proxy (`/v1/*`), not MCP or cloud API

- **Status:** accepted
- **Context:** Bee offers three developer surfaces: the `bee` CLI, an MCP server (`bee mcp
  serve`), and a **local HTTP proxy** (`bee proxy`, binds `127.0.0.1:8787`, forwards
  `/v1/*`, auth handled by `bee login --proxy`). The proxy exposes REST
  (`/v1/conversations`, `/v1/conversations/:id`, `/v1/search/conversations/neural`, …) and
  an SSE stream (`/v1/stream?types=new-utterance,...`).
- **Decision:** The core talks to Bee through the **local proxy over plain HTTP/SSE**.
- **Why not MCP?** MCP is ideal for *an agent* calling Bee interactively, but our core is a
  deterministic data pipeline; REST is simpler to test, replay, and reason about. We can
  still expose our own capabilities over MCP later for the "Agent Skills" angle.
- **Why not the cloud API directly?** The proxy handles auth/session for us and keeps tokens
  off our code path. It also means **zero Node in our codebase** — we only install the CLI.
- **Consequences:** Running a demo requires `bee login` + `bee proxy` to be up. We mitigate
  with a replay source (ADR-010) so development/demo never hard-depends on live Bee.

---

## ADR-004: Core language/runtime = Python

- **Status:** accepted
- **Context:** The coaching layer is LLM-shaped; the vitals layer is XML/JSON parsing and
  time-series math; Bee is consumed over localhost REST. The user is already productive in
  Python (prior project uses Matplotlib/pandas/APIs).
- **Decision:** **Python 3.10+** for the entire core. Bee's CLI is Node, but we consume it
  over REST, so no Node code lives in our repo.
- **Consequences:** Best-in-class ecosystem for HTTP, XML, time-series, and the Anthropic
  SDK. The companion app is the only non-Python piece, by necessity (see ADR-006).

---

## ADR-005: Concept-agnostic core; verticals are plugins

- **Status:** accepted
- **Context:** The PDF's top two concepts (Composure AI, NeuroLearn) share ~80% of their
  plumbing: ingest conversation + vitals, align by time, detect moments, coach. The user
  chose to build the **shared core first** and pick a vertical later.
- **Decision:** No interview/study-specific logic in the core. Domain-specific behavior
  enters only through **pluggable `Detector`s** and **coach prompt profiles**.
- **Consequences:** Slightly more upfront abstraction, but either vertical becomes a small
  add-on. Avoids rework if the demo focus changes.

---

## ADR-006: Live vitals via a watchOS/iOS companion app (primary), with fallbacks

- **Status:** accepted
- **Context:** HealthKit data **cannot be read from a laptop** — only from an authorized
  Apple app. The user opted to build a companion app for near-real-time vitals.
- **Decision:** Three vitals ingestion paths behind one interface (`VitalsSource`):
  1. **Companion app (primary):** watchOS reads HealthKit, posts `VitalSample`s to the
     core's `POST /ingest/vitals` endpoint (ADR-009).
  2. **Apple Health export (batch fallback):** parse `export.xml` — works today, no signing.
  3. **Synthetic generator (offline/demo):** deterministic fake vitals so the pipeline runs
     with zero hardware.
- **Consequences:** Adds a Swift/Xcode deliverable. The core stays agnostic: it receives
  canonical `VitalSample`s regardless of origin. Device signing/provisioning is the user's
  step in Xcode (documented in `companion/README.md`).

---

## ADR-007: One canonical, source-agnostic domain model

- **Status:** accepted
- **Context:** Bee JSON, HealthKit samples, and synthetic data all describe the same
  underlying things but with different shapes, field names, and timestamp formats.
- **Decision:** Define a single **canonical model** (`attune.models`, Pydantic v2):
  `Utterance`, `Conversation`, `VitalSample`, `CheckIn`, `Session`, `Moment`, `Signal`,
  `Recommendation`. **Adapters translate into this model at the boundary**; nothing
  downstream sees raw source formats.
- **Consequences:** The alignment engine, detectors, and coach depend only on the canonical
  model. Adding a new source = writing one adapter.

---

## ADR-008: Timestamps are normalized to UTC epoch milliseconds at the boundary

- **Status:** accepted
- **Context:** Bee uses epoch ms; HealthKit uses ISO-8601 with timezone offsets; synthetic
  data is whatever we choose. Joining two streams on time is the heart of the product, so
  timestamp handling must be unambiguous.
- **Decision:** Every adapter converts to **UTC epoch milliseconds (`int`)** on the way in.
  The canonical model stores only `ts_ms`. Human-facing formatting happens at the edges.
- **Consequences:** Alignment math is pure integer arithmetic. No timezone bugs in the core.

---

## ADR-009: FastAPI ingestion service is the contract between app and core

- **Status:** accepted
- **Context:** The companion app needs somewhere to send vitals; the demo needs a way to
  trigger a pipeline run and read results.
- **Decision:** A small **FastAPI** app (`attune.api`) exposes:
  `POST /ingest/vitals` (companion app → core), `POST /ingest/checkin`,
  `GET /sessions`, `POST /run`, `GET /health`. The request body for `/ingest/vitals` **is**
  the canonical `VitalSample` schema, so the app and core share one contract.
- **Consequences:** The Swift app and the Python core are decoupled by an HTTP schema we
  control and version. Easy to test with `curl`.

---

## ADR-010: Every source has a replay/synthetic twin

- **Status:** accepted
- **Context:** Hackathon demos fail when they depend on live hardware, logins, or networks.
- **Decision:** Ship `BeeReplaySource` (reads recorded fixtures) and `SyntheticVitalsSource`
  alongside the live `BeeProxySource` and `HealthExportSource`. The active source is chosen
  by config (ADR-012), defaulting to **synthetic** so a fresh clone runs instantly.
- **Consequences:** `attune run --source synthetic` works with zero setup. The same pipeline
  code runs against live or replayed data.

---

## ADR-011: Analysis is baseline-relative; no emotion/stress inference (ethics)

- **Status:** accepted
- **Context:** The PDF is emphatic (and the science agrees): an Apple Watch does **not** read
  nervous-system activity or thoughts; HRV alone is not a reliable stress quantifier; and the
  app must never equate elevated heart rate with confusion or anxiety. Framing is **private
  coaching / wellness**, never diagnosis or employer evaluation.
- **Decision:** The core computes signals **only relative to the user's personal baseline**
  (e.g. "HR was elevated vs. this session's earlier readings"), never against population
  thresholds, and the coach layer is bound by enforced guardrails (`attune.coach.guardrails`)
  that forbid emotional/diagnostic claims. See `docs/ETHICS.md`.
- **Consequences:** Outputs are phrased as observations + suggestions, not verdicts. This is
  a correctness constraint enforced in code, not just a guideline.

---

## ADR-012: Configuration is environment-driven (12-factor)

- **Status:** accepted
- **Context:** The same code runs in three modes (live / replay / synthetic) across the
  user's laptop and (later) a deployed demo.
- **Decision:** A single `Settings` object (`attune.config`, pydantic-settings) reads from
  environment / `.env`. No source selection or secrets are hard-coded.
- **Consequences:** `cp .env.example .env` and go. Secrets (Anthropic key) never touch git.

---

## ADR-013: Persistence = SQLite via a thin store

- **Status:** accepted
- **Context:** We need to persist canonical records (especially vitals streamed from the
  app) and query them by time range, with zero infrastructure.
- **Decision:** A single-file **SQLite** database behind a small `store` module. Rows are the
  canonical models serialized to JSON in typed tables keyed by `ts_ms`.
- **Consequences:** Zero setup, survives restarts, trivial to inspect. Can be swapped for
  Postgres later without touching callers (the store is an interface).

---

## ADR-014: Coaching LLM = Claude (Anthropic), guardrailed

- **Status:** accepted
- **Context:** The coach turns aligned moments into personalized, *appropriately hedged*
  recommendations — a language task.
- **Decision:** Use **Claude via the Anthropic SDK**. The exact model id and SDK usage are
  pinned in code and verified against the `claude-api` reference. Guardrails (ADR-011) are
  injected into the system prompt **and** checked post-hoc.
- **Consequences:** Requires `ANTHROPIC_API_KEY`. A deterministic "template coach" fallback
  exists so the pipeline still produces output without a key (for offline demos/tests).

---

## ADR-015: Engineering decisions live in-repo as ADR markdown

- **Status:** accepted
- **Context:** The user asked to "document each decision on the way." These are engineering
  decisions that must version alongside the code and survive independently of any chat.
- **Decision:** Keep this `docs/DECISIONS.md` ADR log in the repository (not in an external
  doc tool). Narrative architecture lives in `docs/ARCHITECTURE.md`.
- **Consequences:** Decisions are reviewable in diffs and PRs, co-located with what they
  govern.

---

## ADR-016: Working codename = "Attune"

- **Status:** provisional
- **Context:** The core is concept-agnostic, so it shouldn't carry a vertical name
  (NeuroLearn / Composure AI are *verticals*, not the platform).
- **Decision:** Use **"Attune"** as the Python package / working codename — it evokes
  "attuning to your state" without committing to a use case. Trivial to rename (one package).
- **Consequences:** Imports read `from attune import ...`. Rename later if a better product
  name emerges.

---

## ADR-017: The coach is free by default; paid LLM is strictly opt-in

- **Status:** accepted (refines ADR-014)
- **Context:** The team needs this to cost **nothing** to build and demo. The only component
  that could incur cost is an LLM API. ADR-014 originally gated the coach on the presence of
  an API key, which risks a surprise charge if a key happens to be in the environment.
- **Decision:** Replace key-presence gating with an explicit ``coach_backend`` setting with
  three options, defaulting to the free one:
  - **``template`` (default):** deterministic, offline, zero cost, zero setup, no key. Produces
    guardrail-compliant recommendations from the detector signals. The demo is fully
    functional on this alone.
  - **``ollama``:** a local LLM via [Ollama](https://ollama.com) — free, runs on the user's
    machine, for nicer natural-language phrasing with no API bill.
  - **``anthropic``:** Claude via the Anthropic API — the only path that spends money, and it
    runs **only** when explicitly selected. (Amazon/Bee hackathons typically provide API
    credits if the team later wants it.)
- **Consequences:** No code path can incur cost unless the user sets
  ``ATTUNE_COACH_BACKEND=anthropic``. The pipeline's quality degrades gracefully across
  backends; ``scrub()`` guardrails (ADR-011) apply identically to all three.

---

## ADR-018: Companion app ships as Swift sources + an Xcode setup guide

- **Status:** accepted
- **Context:** The companion app (ADR-006) needs a watchOS + iOS Xcode project with HealthKit
  entitlements, Info.plist usage strings, and two targets. A hand-authored `project.pbxproj`
  is notoriously fragile — a single wrong hash and Xcode refuses to open it — and cannot be
  verified without Xcode, which isn't available in this environment.
- **Decision:** Ship **correct, idiomatic Swift source files** organized by target
  (`Shared/`, `AttuneiOS/`, `AttuneWatch/`) plus a precise, step-by-step
  `companion/README.md` for assembling the project in Xcode (create targets, set membership,
  add HealthKit capability, Info.plist keys, ATS exception, signing, backend URL).
- **Consequences:** The user does a ~30-second Xcode project creation and drags the files in.
  The code is reviewable and correct now; the build/sign step (which genuinely requires their
  Apple ID and a device) stays with them. The app and core remain decoupled by the HTTP
  schema (ADR-009), so the Swift side can be developed independently of the Python core.

---

## ADR-019: Two vitals paths from the Watch — live (app) and batch (export)

- **Status:** accepted (clarifies ADR-006)
- **Context:** The Apple Watch's signals reach a laptop two ways: the companion app pushing
  live samples, or an Apple Health export file read in batch. The user confirmed the sensor
  signals belong to the Apple Watch side only (Bee carries no vitals — ADR-002).
- **Decision:** Support both behind the one `VitalsSource` contract, plus synthetic:
  `api` (companion app → `/ingest/vitals` → store), `health_export` (parse `export.xml`),
  `synthetic` (offline). The core treats all three identically once samples are canonical.
- **Consequences:** The live demo uses the app; a no-signing fallback uses an export; a
  no-hardware demo uses synthetic. None is privileged in the core.

---

## ADR-020: Self-report check-ins are a first-class, authoritative signal

- **Status:** accepted (realizes ETHICS rule 4)
- **Context:** The PDF repeatedly pairs physiology with **self-reported difficulty** ("you
  reported feeling overwhelmed", "your app asks how difficult the session felt"). ETHICS rule
  4 states the user's own self-report outranks any inferred signal — but the first cut only
  had the `CheckIn` model and a `/ingest/checkin` endpoint; the aligner, detectors, and coach
  ignored them, so the principle wasn't actually in effect.
- **Decision:** Wire check-ins through the whole pipeline:
  - `Moment` gains a `checkin` field; the **aligner** binds each check-in to its *single*
    nearest moment (one-to-one, within the alignment window) so one report can't inflate
    several moments.
  - A new **`CheckInDetector`** (first in the stack) emits a `self_report` signal at the
    **maximum weight (1.0)**, so a self-reported moment ranks above anything inferred.
  - The **coach** (template + LLM prompt) leads with the self-report when present and treats
    it as authoritative.
  - The pipeline reads check-ins from the store (the real app path via `/ingest/checkin`) and,
    in synthetic mode, seeds one near the hard moment for the demo.
- **Consequences:** The product now does what the ethics doc promises — the human's own read
  outranks the machine's inference — and the demo shows a recommendation that opens with
  "You rated … 4/5" rather than a vitals guess. Covered by tests
  (`test_self_report_ranks_top_and_is_coached`, `test_checkin_detector_is_authoritative`).

---

## ADR-021: CI via GitHub Actions (lint + test + CLI smoke)

- **Status:** accepted
- **Context:** The repo should stay green and prove the free, no-hardware path keeps working as
  people (teammates, a friend picking it up) change it.
- **Decision:** A GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and
  PR to `main`: install the core editable with dev deps, `ruff check`, `pytest`, and a CLI
  smoke test (`attune run --json` + `attune version`) across Python 3.10/3.11/3.12. The Swift
  companion app is **not** built in CI — it ships as source assembled in Xcode (ADR-018), so
  there is no buildable project to compile on a runner.
- **Consequences:** A red badge means something broke; the default demo path is continuously
  verified on three Python versions. macOS/Xcode build checks can be added later if the
  companion app graduates to a committed `.xcodeproj`.

## ADR-022: Pick NeuroLearn as the first vertical

- **Status:** accepted
- **Context:** The base layer is complete, tested, and still concept-agnostic. The remaining
  hackathon step is to choose one product story and add its detector/coach specialization.
  The current synthetic/replay data already models a learning session: system-design practice,
  explicit "I don't understand" language, a self-reported difficulty check-in, and topics the
  learner wants to review.
- **Decision:** Ship **NeuroLearn** as the default vertical. `ATTUNE_VERTICAL=neurolearn`
  enables study-specific detectors:
  - `StudyObjectiveDetector` finds moments where the learner explicitly names something to
    review, study, practice, or revisit.
  - `ConceptLinkDetector` finds utterances that connect multiple study concepts, creating a
    small review-map signal.
  The coach receives a NeuroLearn profile that prefers concrete study actions: short review
  blocks, retrieval practice, teach-back, and concept maps. `ATTUNE_VERTICAL=generic` keeps
  the reusable Attune detector stack available for other concepts such as Composure AI.
- **Consequences:** The demo is now a complete product path rather than only a platform:
  Bee captures the study conversation, Watch data remains baseline-relative context,
  self-report remains authoritative, and recommendations are framed as private learning
  support. The specialization is covered by tests for both the NeuroLearn and generic paths.

---

## ADR-023: A software Watch simulator + a readiness `doctor` for watch testing

- **Status:** accepted
- **Context:** Getting onto a real Apple Watch requires an Xcode build, signing, a device, and
  the laptop reachable on the LAN — several steps that each fail silently. We wanted to (a)
  exercise the whole server → store → dashboard loop **before** the app exists and (b) make the
  remaining steps explicit.
- **Decision:** Add `attune simulate-watch` (a `WatchSimulator` that POSTs canonical vitals to
  a running server, as `source="simulated_watch"`, either backfilling a window or streaming
  live), `attune doctor` (prints a readiness checklist: LAN IP + the exact URL to paste into
  the app, `vitals_source`, whether a server/Bee proxy is reachable), and `attune serve --lan`
  (binds `0.0.0.0` and prints the LAN URL). A tiny `netutil.lan_ip()` discovers the address.
- **Consequences:** The demo and the pipeline can be fully exercised with zero hardware, and
  the real-Watch path is reduced to a short, printed checklist. The simulator is canonical, so
  nothing downstream distinguishes it from the real app.

---

## ADR-024: Live dashboard — heart-rate chart, BPM tile, check-ins, live mode

- **Status:** accepted
- **Context:** The static dashboard ran an analysis on demand but didn't show the physiology
  as it arrived, and (bug) it read `moment.salience`, which wasn't serialized — so moments and
  recommendations silently failed to render in a browser.
- **Decision:** 
  - **Bug fix:** make `Moment.salience` a Pydantic `@computed_field` so it ships in the JSON.
  - **Bug fix:** make vitals ingestion idempotent (`INSERT OR IGNORE` on
    `(ts_ms, type, source)`) so re-runs and live polling don't accumulate duplicates.
  - **Feature:** `GET /vitals/recent` (downsampled HR/HRV series) powers a new inline-SVG chart
    with **heart-rate and an HRV trend line on its own scale** (HRV moves inversely to HR, so
    the dip aligns with the HR spike), the salient-moment markers overlaid, a live BPM tile,
    one-tap check-in buttons (1–5) that POST `/ingest/checkin`, and a "Live" toggle that re-runs
    every few seconds — so a streaming Watch updates the page in near real time.
- **Consequences:** The dashboard mirrors the PDF's "physiology alongside the conversation
  moment" concept and is demo-ready. The check-in buttons make the authoritative self-report
  signal (ADR-020) interactive.

---

## ADR-025: Live dashboard is push-based (Server-Sent Events), not polling

- **Status:** accepted (supersedes the polling half of ADR-024)
- **Context:** Live mode re-ran `/run` every 4 seconds. That lags behind arriving samples,
  wastes work when nothing changed, and scales poorly. We want the chart/BPM to update the
  instant a Watch sample lands.
- **Decision:** Add a `GET /events` **Server-Sent Events** stream backed by a tiny in-process
  pub/sub `Broker` (`attune.events`). The sync ingest handlers publish `vitals` / `checkin`
  events after storing; `publish()` is thread-safe (ingest runs in a threadpool, subscribers
  live on the event loop, so it hands each subscriber a `call_soon_threadsafe`). The dashboard's
  Live toggle opens an `EventSource`: on each `vitals` event it updates the BPM tile instantly
  and refreshes the chart, and **debounces** the heavier `/run` to at most once every few
  seconds. A 15s heartbeat keeps idle connections open. No new dependency (plain
  `StreamingResponse`).
- **Consequences:** Near-real-time updates with far less work; the browser auto-reconnects if
  the stream drops. Single-process only — a multi-worker deployment would back the broker with
  Redis behind the same interface. The debounced `/run` keeps recommendations fresh without
  recomputing on every sample.

<!-- Append new ADRs below as decisions are made. Never rewrite history; supersede instead. -->
