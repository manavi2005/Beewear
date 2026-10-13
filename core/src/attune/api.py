"""FastAPI ingestion + run service (ADR-009).

This is the contract between the Swift companion app and the Python core. The app POSTs
canonical :class:`VitalSample` objects to ``/ingest/vitals``; the ``/run`` endpoint executes
the pipeline over a time range and returns a :class:`PipelineResult`.

Run it:  ``uvicorn attune.api:app --reload``  (or ``attune serve``).

A fresh :class:`Store` is opened per request because SQLite connections are not safe to share
across threads — simplest correct choice for a hackathon service.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from attune.config import get_settings
from attune.events import broker
from attune.models import CheckIn, VitalSample, VitalType
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
      grid-template-rows: 172px minmax(180px, .85fr) minmax(220px, 1fr);
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
    /* live BPM tile + live toggle */
    .bpm { display: flex; align-items: baseline; gap: 6px; color: var(--danger); }
    .bpm b { font-size: 22px; line-height: 1; font-variant-numeric: tabular-nums; }
    .bpm span { font-size: 12px; color: var(--muted); }
    .heart { color: var(--danger); animation: beat 1s ease-in-out infinite; }
    @keyframes beat { 0%,100% { transform: scale(1); } 15% { transform: scale(1.25); } }
    .ghost { background: var(--panel); color: var(--ink); border-color: var(--line); }
    .ghost.on { background: var(--danger); color: #fff; border-color: var(--danger); }
    /* check-in control */
    .checkin { padding: 11px 14px; border-bottom: 1px solid var(--line); display: grid; gap: 7px; }
    .checkin > span { color: var(--muted); font-size: 12px; }
    .rate { display: flex; gap: 6px; }
    .rate button {
      flex: 1; min-height: 30px; padding: 0; background: var(--soft); color: var(--ink);
      border: 1px solid var(--line); font-weight: 700;
    }
    .rate button:hover { background: #e7f1ee; border-color: var(--accent); }
    /* HR chart */
    .chart-panel { grid-template-rows: auto 1fr; }
    .chartwrap { padding: 8px 12px 12px; min-height: 0; }
    #chart { width: 100%; height: 100%; display: block; }
    .chart-grid { stroke: var(--line); stroke-width: 1; }
    .chart-line { fill: none; stroke: var(--danger); stroke-width: 2; }
    .chart-area { fill: var(--danger); opacity: .07; }
    .chart-marker { stroke: var(--accent); stroke-width: 1.5; stroke-dasharray: 3 3; }
    .chart-dot { fill: var(--accent); }
    .chart-label { fill: var(--muted); font-size: 10px; }
    .chart-hrv { fill: none; stroke: var(--blue); stroke-width: 1.5; opacity: .9; }
    .chart-title { display: flex; align-items: baseline; gap: 12px; min-width: 0; }
    .legend {
      display: inline-flex; align-items: center; gap: 10px;
      color: var(--muted); font-size: 12px;
    }
    .legend .pair { display: inline-flex; align-items: center; gap: 5px; }
    .sw {
      width: 14px; height: 0; display: inline-block;
      border-top: 2px solid transparent;
    }
    .sw.hr { border-color: var(--danger); }
    .sw.hrv { border-color: var(--blue); }
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
        <div class="bpm" title="most recent heart rate">
          <span class="heart">♥</span><b id="bpm">—</b><span>bpm</span>
        </div>
        <label class="field">
          Lookback
          <input id="lookback" type="number" min="5" max="240" step="5" value="60" />
          min
        </label>
        <button id="live" class="ghost" title="auto-refresh every few seconds">● Live</button>
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
        <div class="checkin">
          <span>How hard did that feel? (sends a self-report now)</span>
          <div class="rate">
            <button data-val="1">1</button>
            <button data-val="2">2</button>
            <button data-val="3">3</button>
            <button data-val="4">4</button>
            <button data-val="5">5</button>
          </div>
        </div>
        <div class="signals" id="signals"></div>
      </aside>
      <section class="workspace">
        <section class="panel chart-panel">
          <div class="section-head">
            <div class="chart-title">
              <h2>Heart rate &amp; HRV <span class="stamp">vs. your own baseline</span></h2>
              <span class="legend">
                <span class="pair"><span class="sw hr"></span>HR</span>
                <span class="pair"><span class="sw hrv"></span>HRV</span>
              </span>
            </div>
            <span class="stamp" id="chartmeta"></span>
          </div>
          <div class="chartwrap">
            <svg id="chart" viewBox="0 0 600 150" preserveAspectRatio="none"
              xmlns="http://www.w3.org/2000/svg"></svg>
          </div>
        </section>
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

    let lastMoments = [];
    let eventSource = null;
    let runDebounce = null;

    function renderBpm(v) {
      $("bpm").textContent = (v.latest_bpm == null) ? "—" : Math.round(v.latest_bpm);
    }

    function renderChart(v, moments) {
      const svg = $("chart");
      const W = 600, H = 150, pad = 6;
      const hr = v.heart_rate || [];
      if (hr.length < 2) {
        svg.innerHTML = "";
        $("chartmeta").textContent = "waiting for vitals — try: attune simulate-watch";
        return;
      }
      const start = v.start_ms, end = v.end_ms, span = Math.max(1, end - start);
      const vals = hr.map(p => p[1]);
      let lo = Math.min(...vals), hi = Math.max(...vals);
      if (hi - lo < 8) { const m = (hi + lo) / 2; lo = m - 4; hi = m + 4; }
      const x = (ts) => ((ts - start) / span) * W;
      const y = (val) => H - pad - ((val - lo) / (hi - lo)) * (H - 2 * pad);
      const pts = hr.map(p => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
      const firstX = x(hr[0][0]).toFixed(1);
      const lastX = x(hr[hr.length - 1][0]).toFixed(1);
      const area = `M${firstX},${H} L${pts.replaceAll(" ", " L")} L${lastX},${H} Z`;

      const nearestY = (ts) => {
        let best = hr[0], bd = Infinity;
        for (const p of hr) { const d = Math.abs(p[0] - ts); if (d < bd) { bd = d; best = p; } }
        return y(best[1]);
      };
      const markers = (moments || [])
        .filter(m => m.ts_ms >= start && m.ts_ms <= end)
        .map(m => {
          const mx = x(m.ts_ms).toFixed(1);
          const cy = nearestY(m.ts_ms).toFixed(1);
          return `<line class="chart-marker" x1="${mx}" y1="0" x2="${mx}" y2="${H}"></line>`
               + `<circle class="chart-dot" cx="${mx}" cy="${cy}" r="3"></circle>`;
        }).join("");

      // HRV trend on its OWN scale (ms; typically moves inversely to heart rate).
      const hrv = v.hrv_sdnn || [];
      let hrvLine = "", hrvMeta = "";
      if (hrv.length >= 2) {
        const hv = hrv.map(p => p[1]);
        let hlo = Math.min(...hv), hhi = Math.max(...hv);
        if (hhi - hlo < 6) { const m = (hhi + hlo) / 2; hlo = m - 3; hhi = m + 3; }
        const yH = (val) => H - pad - ((val - hlo) / (hhi - hlo)) * (H - 2 * pad);
        const hpts = hrv.map(p => `${x(p[0]).toFixed(1)},${yH(p[1]).toFixed(1)}`).join(" ");
        hrvLine = `<polyline class="chart-hrv" points="${hpts}"></polyline>`;
        hrvMeta = ` · HRV ${Math.round(hlo)}–${Math.round(hhi)} ms`;
      }

      const midStr = ((y(lo) + y(hi)) / 2).toFixed(1);
      svg.innerHTML =
        `<line class="chart-grid" x1="0" y1="${midStr}" x2="${W}" y2="${midStr}"></line>`
        + `<path class="chart-area" d="${area}"></path>`
        + `<polyline class="chart-line" points="${pts}"></polyline>`
        + hrvLine
        + markers;
      const now = v.latest_bpm == null ? "—" : Math.round(v.latest_bpm);
      const nMark = (moments || []).filter(m => m.ts_ms >= start && m.ts_ms <= end).length;
      const plural = nMark === 1 ? "" : "s";
      const hrRange = `HR ${Math.round(lo)}–${Math.round(hi)}`;
      $("chartmeta").textContent =
        `${hrRange}${hrvMeta} · now ${now} bpm · ${nMark} moment${plural}`;
    }

    async function loadVitals(lookback) {
      try {
        const v = await fetch(`/vitals/recent?lookback_minutes=${lookback}`).then(r => r.json());
        renderBpm(v);
        renderChart(v, lastMoments);
      } catch (_) { /* leave previous chart */ }
    }

    async function postCheckin(value) {
      try {
        await fetch("/ingest/checkin", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ts_ms: Date.now(), value, label: "self-report",
                                 prompt: "How hard did that feel, 1-5?"})
        });
        $("updated").textContent = `check-in ${value}/5 sent`;
        load();
      } catch (err) { $("updated").textContent = "check-in failed"; }
    }

    function scheduleRun() {
      // Vitals can arrive every couple of seconds; refresh the (heavier) analysis at most
      // once every few seconds, while BPM + chart update instantly below.
      if (runDebounce) return;
      runDebounce = setTimeout(() => { runDebounce = null; load(); }, 4000);
    }

    async function onVitals(e) {
      try {
        const d = JSON.parse(e.data);
        if (d.latest_bpm != null) $("bpm").textContent = Math.round(d.latest_bpm);
        $("updated").textContent = "live " + fmtTime(Date.now());
      } catch (_) { /* ignore malformed */ }
      await loadVitals(Number($("lookback").value || 60));  // instant chart refresh
      scheduleRun();                                        // debounced recommendations
    }

    function onCheckin() { load(); }

    function startLive() {
      if (eventSource) return;
      eventSource = new EventSource("/events");
      eventSource.addEventListener("vitals", onVitals);
      eventSource.addEventListener("checkin", onCheckin);
      eventSource.onerror = () => { $("updated").textContent = "live (reconnecting…)"; };
      $("live").classList.add("on");
      load();  // seed immediately; pushes take over from here
    }

    function stopLive() {
      if (eventSource) { eventSource.close(); eventSource = null; }
      if (runDebounce) { clearTimeout(runDebounce); runDebounce = null; }
      $("live").classList.remove("on");
    }

    function toggleLive() { eventSource ? stopLive() : startLive(); }

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
        lastMoments = result.salient_moments;
        await loadVitals(lookback);
      } catch (err) {
        $("recommendations").innerHTML = `<div class="error">${err.message}</div>`;
        $("updated").textContent = "Error";
      } finally {
        $("run").disabled = false;
      }
    }

    $("run").addEventListener("click", load);
    $("live").addEventListener("click", toggleLive);
    document.querySelectorAll(".rate button").forEach(
      (b) => b.addEventListener("click", () => postCheckin(Number(b.dataset.val)))
    );
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


class VitalsRecent(BaseModel):
    """Downsampled recent vitals for the live dashboard chart (ADR-024)."""

    start_ms: int
    end_ms: int
    latest_bpm: float | None = None
    latest_ms: int | None = None
    heart_rate: list[list[float]] = []  # [[ts_ms, bpm], ...]
    hrv_sdnn: list[list[float]] = []  # [[ts_ms, ms], ...]


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


@app.get("/events")
async def events() -> StreamingResponse:
    """Server-Sent Events: push a message the instant vitals/check-ins are ingested (ADR-025).

    The dashboard's Live mode subscribes here instead of polling, so the chart updates in real
    time. A heartbeat every 15s keeps proxies from closing an idle connection.
    """
    queue = await broker.subscribe()

    async def event_stream():
        yield ": connected\n\n"
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            broker.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering so events flush immediately
        },
    )


@app.post("/ingest/vitals", response_model=IngestResult)
def ingest_vitals(
    samples: list[VitalSample] | VitalSample = Body(...),
) -> IngestResult:
    """Receive one or many vital samples from the companion app (ADR-006/009).

    After storing, push an SSE ``vitals`` event so live dashboards update instantly (ADR-025).
    """
    batch = samples if isinstance(samples, list) else [samples]
    store = _store()
    try:
        n = store.add_vitals(batch)
    finally:
        store.close()
    _publish_vitals(batch, n)
    return IngestResult(ingested=n)


def _publish_vitals(batch: list[VitalSample], ingested: int) -> None:
    """Broadcast a compact 'vitals' SSE event with the latest heart rate in this batch."""
    hr = [s for s in batch if s.type is VitalType.heart_rate]
    latest = max(hr, key=lambda s: s.ts_ms) if hr else None
    broker.publish(
        "vitals",
        {
            "ingested": ingested,
            "latest_bpm": latest.value if latest else None,
            "latest_ms": latest.ts_ms if latest else None,
        },
    )


@app.post("/ingest/checkin", response_model=IngestResult)
def ingest_checkin(checkin: CheckIn) -> IngestResult:
    """Receive a user self-report (first-class signal; ETHICS rule 4), and push an SSE event."""
    store = _store()
    try:
        store.add_checkin(checkin)
    finally:
        store.close()
    broker.publish("checkin", {"ts_ms": checkin.ts_ms, "value": checkin.value})
    return IngestResult(ingested=1)


@app.get("/vitals/recent", response_model=VitalsRecent)
def vitals_recent(lookback_minutes: int = 60, max_points: int = 240) -> VitalsRecent:
    """Recent heart-rate / HRV series (downsampled) for the live chart + BPM tile."""
    start_ms, end_ms = default_window(lookback_minutes)
    store = _store()
    try:
        samples = store.get_vitals(start_ms, end_ms)
    finally:
        store.close()

    hr = sorted(
        ([s.ts_ms, s.value] for s in samples if s.type is VitalType.heart_rate),
        key=lambda p: p[0],
    )
    hrv = sorted(
        ([s.ts_ms, s.value] for s in samples if s.type is VitalType.hrv_sdnn),
        key=lambda p: p[0],
    )
    latest_ms, latest_bpm = (hr[-1][0], hr[-1][1]) if hr else (None, None)
    return VitalsRecent(
        start_ms=start_ms,
        end_ms=end_ms,
        latest_bpm=latest_bpm,
        latest_ms=int(latest_ms) if latest_ms is not None else None,
        heart_rate=_downsample(hr, max_points),
        hrv_sdnn=_downsample(hrv, max_points),
    )


def _downsample(points: list[list[float]], max_points: int) -> list[list[float]]:
    """Keep at most ``max_points`` evenly across the series (last point always kept)."""
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    out = [points[int(i * step)] for i in range(max_points)]
    out[-1] = points[-1]
    return out


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
