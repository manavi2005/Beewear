"""SQLite persistence (ADR-013).

A single-file database behind a thin interface. Canonical models are stored as JSON in
``ts_ms``-keyed tables, which keeps writes trivial and range queries fast without an ORM.
The store is the hand-off point for the companion app: vitals POSTed to the API land here
(ADR-009), and the pipeline reads them back out by time range.

Swapping SQLite for Postgres later means reimplementing this one class; nothing else changes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from attune.models import CheckIn, Conversation, VitalSample

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vitals (
    ts_ms  INTEGER NOT NULL,
    type   TEXT    NOT NULL,
    source TEXT    NOT NULL DEFAULT '',
    data   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vitals_ts ON vitals(ts_ms);
-- Idempotent ingestion: the same sample (same instant, type, device) inserts once, so
-- re-runs and live polling don't accumulate duplicates.
CREATE UNIQUE INDEX IF NOT EXISTS uq_vitals ON vitals(ts_ms, type, source);

CREATE TABLE IF NOT EXISTS conversations (
    id       TEXT PRIMARY KEY,
    start_ms INTEGER NOT NULL,
    end_ms   INTEGER NOT NULL,
    data     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_start ON conversations(start_ms);

CREATE TABLE IF NOT EXISTS checkins (
    ts_ms INTEGER NOT NULL,
    data  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkins_ts ON checkins(ts_ms);
"""


class Store:
    def __init__(self, path: str | Path = "attune.db"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── vitals ──────────────────────────────────────────────────────────────
    def add_vitals(self, samples: list[VitalSample]) -> int:
        """Insert samples, ignoring exact duplicates. Returns the number actually inserted."""
        rows = [(s.ts_ms, s.type.value, s.source, s.model_dump_json()) for s in samples]
        before = self._conn.total_changes
        self._conn.executemany(
            "INSERT OR IGNORE INTO vitals(ts_ms, type, source, data) VALUES (?, ?, ?, ?)", rows
        )
        self._conn.commit()
        return self._conn.total_changes - before

    def get_vitals(self, start_ms: int, end_ms: int) -> list[VitalSample]:
        cur = self._conn.execute(
            "SELECT data FROM vitals WHERE ts_ms BETWEEN ? AND ? ORDER BY ts_ms",
            (start_ms, end_ms),
        )
        return [VitalSample.model_validate_json(r["data"]) for r in cur.fetchall()]

    # ── conversations ─────────────────────────────────────────────────────────
    def upsert_conversations(self, conversations: list[Conversation]) -> int:
        rows = [(c.id, c.start_ms, c.end_ms, c.model_dump_json()) for c in conversations]
        self._conn.executemany(
            "INSERT INTO conversations(id, start_ms, end_ms, data) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET start_ms=excluded.start_ms, "
            "end_ms=excluded.end_ms, data=excluded.data",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def get_conversations(self, start_ms: int, end_ms: int) -> list[Conversation]:
        cur = self._conn.execute(
            "SELECT data FROM conversations WHERE end_ms >= ? AND start_ms <= ? ORDER BY start_ms",
            (start_ms, end_ms),
        )
        return [Conversation.model_validate_json(r["data"]) for r in cur.fetchall()]

    # ── check-ins ───────────────────────────────────────────────────────────
    def add_checkin(self, checkin: CheckIn) -> None:
        self._conn.execute(
            "INSERT INTO checkins(ts_ms, data) VALUES (?, ?)",
            (checkin.ts_ms, checkin.model_dump_json()),
        )
        self._conn.commit()

    def get_checkins(self, start_ms: int, end_ms: int) -> list[CheckIn]:
        cur = self._conn.execute(
            "SELECT data FROM checkins WHERE ts_ms BETWEEN ? AND ? ORDER BY ts_ms",
            (start_ms, end_ms),
        )
        return [CheckIn.model_validate_json(r["data"]) for r in cur.fetchall()]
