"""FastAPI ingestion + run service (ADR-009).

This is the contract between the Swift companion app and the Python core. The app POSTs
canonical :class:`VitalSample` objects to ``/ingest/vitals``; the ``/run`` endpoint executes
the pipeline over a time range and returns a :class:`PipelineResult`.

Run it:  ``uvicorn attune.api:app --reload``  (or ``attune serve``).

A fresh :class:`Store` is opened per request because SQLite connections are not safe to share
across threads — simplest correct choice for a hackathon service.
"""

from __future__ import annotations

from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from attune.config import get_settings
from attune.models import CheckIn, VitalSample
from attune.pipeline import Pipeline, PipelineResult, default_window, now_ms
from attune.store import Store

app = FastAPI(
    title="Attune core",
    version="0.1.0",
    summary="Bee conversation context + Apple Watch physiology, aligned in time.",
)

_INDEX_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NeuroLearn</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17201c;
      --muted: #5d6863;
      --line: #d9dfdc;
      --soft: #f5f7f6;
      --panel: #ffffff;
      --accent: #12715f;
      --accent-2: #b65c31;
      --blue: #2b5f8a;
      --danger: #a23b3b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      color: var(--ink);
      background: #eef2f0;
      letter-spacing: 0;
    }
    button, input { font: inherit; }
    .shell { min-height: 100vh; display: grid; grid-template-rows: auto 1fr; }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 20px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    .brand { display: flex; align-items: baseline; gap: 12px; min-width: 0; }
    h1 { margin: 0; font-size: 22px; line-height: 1.1; font-weight: 760; }
    .subtitle { color: var(--muted); font-size: 13px; white-space: nowrap; }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .field { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px; }
    input {
      width: 78px;
      min-height: 34px;
      padding: 6px 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--ink);
    }
    button {
      min-height: 34px;
      border: 1px solid #0b5f50;
      border-radius: 6px;
      padding: 7px 12px;
      background: var(--accent);
      color: white;
      cursor: pointer;
      font-weight: 650;
    }
    button:disabled { opacity: .65; cursor: wait; }
    main {
      display: grid;
      grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
      gap: 16px;
      padding: 16px;
      height: calc(100vh - 64px);
      min-height: 620px;
    }
    aside, section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    aside { display: grid; grid-template-rows: auto auto 1fr; min-height: 0; }
    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 13px 14px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfb;
    }
    h2 { margin: 0; font-size: 14px; line-height: 1.2; font-weight: 760; }
    .stamp { color: var(--muted); font-size: 12px; }
    .stats {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      border-bottom: 1px solid var(--line);
    }
    .stat {
      padding: 12px 14px;
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
    }
    .stat:nth-child(even) { border-right: 0; }
    .stat:nth-last-child(-n + 2) { border-bottom: 0; }
    .stat b { display: block; font-size: 24px; line-height: 1; }
    .stat span { display: block; margin-top: 6px; color: var(--muted); font-size: 12px; }
    .config { padding: 12px 14px; display: grid; gap: 8px; border-bottom: 1px solid var(--line); }
    .row { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
    .row span:first-child { color: var(--muted); }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 8px;
      border-radius: 999px;
      background: #e7f1ee;
      color: #0d5d4f;
      font-size: 12px;
      font-weight: 700;
    }
    .signals {
      min-height: 0;
      overflow: auto;
      padding: 10px 14px 14px;
    }
    .signal {
      display: grid;
      grid-template-columns: 8px 1fr;
      gap: 10px;
      padding: 8px 0;
      border-bottom: 1px solid #edf0ee;
    }
    .signal:last-child { border-bottom: 0; }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      margin-top: 6px;
      background: var(--accent);
    }
    .dot.self_report { background: var(--accent-2); }
    .dot.vitals_delta { background: var(--blue); }
    .signal b { display: block; font-size: 13px; }
    .signal span { color: var(--muted); font-size: 12px; }
    .workspace {
      display: grid;
      grid-template-rows: minmax(220px, .9fr) minmax(260px, 1.1fr);
      min-height: 0;
      gap: 16px;
      background: transparent;
      border: 0;
      border-radius: 0;
      overflow: visible;
    }
    .panel { min-height: 0; display: grid; grid-template-rows: auto 1fr; }
    .list { overflow: auto; }
    .rec, .moment {
      display: grid;
      gap: 8px;
      padding: 13px 14px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    .rec:last-child, .moment:last-child { border-bottom: 0; }
    .rec-title { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }
    .rec-title b { font-size: 15px; }
    .rank { color: var(--muted); font-size: 12px; }
    .body { font-size: 14px; line-height: 1.45; color: #24312c; }
    .basis { display: flex; flex-wrap: wrap; gap: 6px; }
    .basis span {
      max-width: 100%;
      padding: 3px 7px;
      border: 1px solid #e0e6e3;
      border-radius: 999px;
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .moment { grid-template-columns: 82px minmax(0, 1fr) 72px; align-items: start; }
    .time { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
    .quote { font-size: 14px; line-height: 1.4; }
    .speaker { color: var(--muted); font-size: 12px; margin-bottom: 3px; }
    .score {
      text-align: right;
      font-size: 13px;
      font-variant-numeric: tabular-nums;
      color: var(--blue);
      font-weight: 760;
    }
    .chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
    .chip {
      padding: 2px 6px;
      border-radius: 999px;
      background: var(--soft);
      color: var(--muted);
      font-size: 11px;
    }
    .empty, .error { padding: 18px 14px; color: var(--muted); font-size: 14px; }
    .error { color: var(--danger); }
    @media (max-width: 860px) {
      header { align-items: flex-start; flex-direction: column; }
      .toolbar { justify-content: flex-start; }
      main { grid-template-columns: 1fr; height: auto; min-height: 0; }
      .workspace { grid-template-rows: auto auto; }
      aside, .panel { max-height: none; }
      .subtitle { white-space: normal; }
      .moment { grid-template-columns: 70px minmax(0, 1fr); }
      .score { grid-column: 2; text-align: left; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">
        <h1>NeuroLearn</h1>
        <div class="subtitle">Bee conversation + Watch context study coach</div>
      </div>
      <div class="toolbar">
        <label class="field">
          Lookback
          <input id="lookback" type="number" min="5" max="240" step="5" value="60" />
          min
        </label>
        <button id="run">Run Analysis</button>
      </div>
    </header>
    <main>
      <aside>
        <div class="section-head">
          <h2>Session</h2>
          <span class="stamp" id="updated">Idle</span>
        </div>
        <div class="stats">
          <div class="stat"><b id="utterances">0</b><span>utterances</span></div>
          <div class="stat"><b id="vitals">0</b><span>vitals</span></div>
          <div class="stat"><b id="checkins">0</b><span>check-ins</span></div>
          <div class="stat"><b id="recs">0</b><span>recommendations</span></div>
        </div>
        <div class="config" id="config"></div>
        <div class="signals" id="signals"></div>
      </aside>
      <section class="workspace">
        <section class="panel">
          <div class="section-head">
            <h2>Recommendations</h2>
            <span class="pill" id="coach">template</span>
          </div>
          <div class="list" id="recommendations"></div>
        </section>
        <section class="panel">
          <div class="section-head">
            <h2>Salient Moments</h2>
            <span class="stamp" id="window"></span>
          </div>
          <div class="list" id="moments"></div>
        </section>
      </section>
    </main>
  </div>
  <script>
    const $ = (id) => document.getElementById(id);
    const fmtTime = (ms) => new Date(ms).toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
    const titleCase = (s) => s.replaceAll("_", " ").replace(/\\b\\w/g, c => c.toUpperCase());

    function setConfig(health) {
      $("config").innerHTML = [
        ["Vertical", health.vertical],
        ["Conversation", health.conversation_source],
        ["Vitals", health.vitals_source],
        ["Coach", health.coach_backend]
      ].map(([k, v]) => `<div class="row"><span>${k}</span><b>${v}</b></div>`).join("");
      $("coach").textContent = health.coach_backend;
    }

    function renderSignals(moments) {
      const counts = new Map();
      for (const m of moments) {
        for (const s of m.signals || []) counts.set(s.kind, (counts.get(s.kind) || 0) + 1);
      }
      const rows = [...counts.entries()].sort((a, b) => b[1] - a[1]);
      $("signals").innerHTML = rows.length ? rows.map(([kind, count]) => `
        <div class="signal">
          <span class="dot ${kind}"></span>
          <div><b>${titleCase(kind)}</b><span>${count} signal${count === 1 ? "" : "s"}</span></div>
        </div>
      `).join("") : `<div class="empty">No signals yet.</div>`;
    }

    function renderRecommendations(items) {
      $("recommendations").innerHTML = items.length ? items.map((rec, i) => `
        <article class="rec">
          <div class="rec-title"><b>${rec.title}</b><span class="rank">#${i + 1}</span></div>
          <div class="body">${rec.body}</div>
          <div class="basis">
            ${(rec.basis || []).slice(0, 4).map(
              b => `<span title="${b}">${b}</span>`
            ).join("")}
          </div>
        </article>
      `).join("") : `<div class="empty">No recommendations.</div>`;
    }

    function renderMoments(items) {
      $("moments").innerHTML = items.length ? items.map((m) => {
        const kinds = [...new Set((m.signals || []).map(s => s.kind))];
        return `
          <article class="moment">
            <div class="time">${fmtTime(m.ts_ms)}</div>
            <div>
              <div class="speaker">${m.utterance.speaker || "me"}</div>
              <div class="quote">${m.utterance.text}</div>
              <div class="chips">
                ${kinds.map(k => `<span class="chip">${titleCase(k)}</span>`).join("")}
              </div>
            </div>
            <div class="score">${m.salience.toFixed(2)}</div>
          </article>
        `;
      }).join("") : `<div class="empty">No salient moments.</div>`;
    }

    async function load() {
      $("run").disabled = true;
      $("updated").textContent = "Running";
      try {
        const health = await fetch("/health").then(r => r.json());
        setConfig(health);
        const lookback = Number($("lookback").value || 60);
        const result = await fetch("/run", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({lookback_minutes: lookback})
        }).then(r => r.json());
        $("utterances").textContent = result.n_utterances;
        $("vitals").textContent = result.n_vitals;
        $("checkins").textContent = result.n_checkins;
        $("recs").textContent = result.recommendations.length;
        $("window").textContent = `${fmtTime(result.start_ms)} - ${fmtTime(result.end_ms)}`;
        $("updated").textContent = fmtTime(Date.now());
        renderSignals(result.salient_moments);
        renderRecommendations(result.recommendations);
        renderMoments(result.salient_moments);
      } catch (err) {
        $("recommendations").innerHTML = `<div class="error">${err.message}</div>`;
        $("updated").textContent = "Error";
      } finally {
        $("run").disabled = false;
      }
    }

    $("run").addEventListener("click", load);
    load();
  </script>
</body>
</html>
"""


def _store() -> Store:
    return Store(get_settings().db_path)


class Health(BaseModel):
    status: str = "ok"
    vertical: str
    coach_backend: str
    conversation_source: str
    vitals_source: str
    server_time_ms: int


class IngestResult(BaseModel):
    ingested: int


class RunRequest(BaseModel):
    start_ms: int | None = None
    end_ms: int | None = None
    lookback_minutes: int = 60


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Local browser UI for the NeuroLearn demo."""
    return _INDEX_HTML


@app.get("/health", response_model=Health)
def health() -> Health:
    s = get_settings()
    return Health(
        vertical=s.vertical,
        coach_backend=s.coach_backend,
        conversation_source=s.conversation_source,
        vitals_source=s.vitals_source,
        server_time_ms=now_ms(),
    )


@app.post("/ingest/vitals", response_model=IngestResult)
def ingest_vitals(
    samples: list[VitalSample] | VitalSample = Body(...),
) -> IngestResult:
    """Receive one or many vital samples from the companion app (ADR-006/009)."""
    batch = samples if isinstance(samples, list) else [samples]
    store = _store()
    try:
        n = store.add_vitals(batch)
    finally:
        store.close()
    return IngestResult(ingested=n)


@app.post("/ingest/checkin", response_model=IngestResult)
def ingest_checkin(checkin: CheckIn) -> IngestResult:
    """Receive a user self-report (first-class signal; ETHICS rule 4)."""
    store = _store()
    try:
        store.add_checkin(checkin)
    finally:
        store.close()
    return IngestResult(ingested=1)


@app.post("/run", response_model=PipelineResult)
def run(req: RunRequest = Body(default_factory=RunRequest)) -> PipelineResult:
    """Run the full pipeline over a window and return moments + recommendations."""
    if req.start_ms is not None and req.end_ms is not None:
        start_ms, end_ms = req.start_ms, req.end_ms
    else:
        start_ms, end_ms = default_window(req.lookback_minutes)
    store = _store()
    try:
        return Pipeline(store=store).run(start_ms, end_ms)
    finally:
        store.close()
