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


def _store() -> Store:
    return Store(get_settings().db_path)


class Health(BaseModel):
    status: str = "ok"
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


@app.get("/health", response_model=Health)
def health() -> Health:
    s = get_settings()
    return Health(
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
