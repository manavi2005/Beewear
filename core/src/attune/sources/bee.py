"""Live Bee conversation source via the local HTTP proxy (ADR-003).

Prerequisites (run once, then leave the proxy running):

    npm install -g @beeai/cli
    bee login            # enable Developer Mode in the Bee app first
    bee proxy --port 8787

The proxy binds 127.0.0.1:8787 and forwards ``/v1/*``; it handles auth, so we send no
tokens from here.

IMPLEMENTATION NOTE — field names: Bee's public docs confirm the *routes* and that
conversations carry summaries and a transcript, but do not pin every JSON field name.
All source-specific field access is therefore funnelled through ``_parse_conversation`` /
``_parse_utterance`` / ``_to_ms`` below, each of which tries several plausible keys. If a
real account returns different names, fix them in exactly one place here — nothing else in
the codebase touches raw Bee JSON (ADR-007).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from typing import Any

import httpx

from attune.models import Conversation, Utterance, VitalType  # noqa: F401 (VitalType re-export)


def _to_ms(value: Any) -> int | None:
    """Normalize a Bee timestamp (epoch s, epoch ms, or ISO-8601) to UTC epoch ms (ADR-008)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Heuristic: >1e12 is already ms; otherwise seconds.
        return int(value) if value > 1e12 else int(value * 1000)
    if isinstance(value, str):
        v = value.strip()
        if v.isdigit():
            return _to_ms(int(v))
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            return None
    return None


def _first(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


class BeeProxySource:
    """Reads conversations + transcripts from a running ``bee proxy``."""

    name = "bee"

    def __init__(self, proxy_url: str = "http://127.0.0.1:8787", timeout_s: float = 15.0):
        self.base = proxy_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base, timeout=timeout_s)

    # ── public API ────────────────────────────────────────────────────────────
    def fetch(self, start_ms: int, end_ms: int) -> Iterable[Conversation]:
        out: list[Conversation] = []
        for raw in self._iter_conversations():
            conv = self._parse_conversation(raw)
            if conv is None:
                continue
            # Keep conversations that overlap the requested window.
            if conv.end_ms < start_ms or conv.start_ms > end_ms:
                continue
            if not conv.utterances:
                conv = self._hydrate_transcript(conv)
            out.append(conv)
        return out

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BeeProxySource:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── HTTP ───────────────────────────────────────────────────────────────────
    def _iter_conversations(self) -> Iterator[dict[str, Any]]:
        """GET /v1/conversations, following ``next_cursor`` pagination."""
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            resp = self._client.get("/v1/conversations", params=params)
            resp.raise_for_status()
            data = resp.json()
            items = _first(data, "conversations", "items", "data", default=[]) or []
            yield from items
            cursor = _first(data, "next_cursor", "cursor")
            if not cursor:
                break

    def _hydrate_transcript(self, conv: Conversation) -> Conversation:
        """GET /v1/conversations/:id to pull the transcript/utterances."""
        resp = self._client.get(f"/v1/conversations/{conv.id}")
        resp.raise_for_status()
        detail = resp.json()
        detail = _first(detail, "conversation", default=detail)
        raw_utts = _first(detail, "transcript", "utterances", "lines", default=[]) or []
        conv.utterances = [
            u for u in (self._parse_utterance(r, conv.id) for r in raw_utts) if u is not None
        ]
        return conv

    # ── parsing (the ONLY place that knows Bee's JSON shape) ─────────────────────
    def _parse_conversation(self, raw: dict[str, Any]) -> Conversation | None:
        cid = _first(raw, "id", "conversation_id", "uuid")
        if cid is None:
            return None
        start = _to_ms(_first(raw, "start_time", "start", "created_at", "startedAt"))
        end = _to_ms(_first(raw, "end_time", "end", "ended_at", "endedAt", "updated_at")) or start
        if start is None:
            return None
        summary = _first(raw, "short_summary", "summary", "title")
        raw_utts = _first(raw, "transcript", "utterances", default=[]) or []
        utts = [u for u in (self._parse_utterance(r, str(cid)) for r in raw_utts) if u]
        return Conversation(
            id=str(cid),
            start_ms=start,
            end_ms=end or start,
            summary=summary,
            utterances=utts,
        )

    def _parse_utterance(self, raw: dict[str, Any], conv_id: str) -> Utterance | None:
        ts = _to_ms(_first(raw, "start", "time", "ts", "timestamp", "created_at"))
        text = _first(raw, "text", "content", "transcript", default="")
        if ts is None or not text:
            return None
        speaker = str(_first(raw, "speaker", "speaker_label", "role", default=""))
        uid = str(_first(raw, "id", "uuid", default=f"{conv_id}-{ts}"))
        return Utterance(
            id=uid, ts_ms=ts, speaker=speaker, text=str(text), conversation_id=conv_id
        )
