"""Replay recorded Bee conversations from a fixture (ADR-010).

This is the offline twin of :class:`~attune.sources.bee.BeeProxySource`: identical output
type (canonical :class:`Conversation`), but read from a JSON fixture instead of the live
proxy. Useful for demos on a plane and for deterministic tests.

The fixture is a JSON list of canonical ``Conversation`` objects. On load we **re-anchor**
all timestamps so the latest utterance lands at the window's ``end_ms`` — the same trick the
synthetic source uses, so a replayed conversation always falls inside a default lookback
window regardless of when it was recorded.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from attune.models import Conversation

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
_DEFAULT_FIXTURE = _FIXTURES / "bee_conversations_sample.json"


class BeeReplaySource:
    name = "replay"

    def __init__(self, fixture_path: str | Path | None = None):
        self.fixture_path = Path(fixture_path) if fixture_path else _DEFAULT_FIXTURE

    def fetch(self, start_ms: int, end_ms: int) -> Iterable[Conversation]:
        convs = self._load()
        if not convs:
            return []
        convs = self._reanchor(convs, end_ms)
        return [c for c in convs if not (c.end_ms < start_ms or c.start_ms > end_ms)]

    def _load(self) -> list[Conversation]:
        if not self.fixture_path.exists():
            return []
        raw = json.loads(self.fixture_path.read_text())
        return [Conversation.model_validate(c) for c in raw]

    @staticmethod
    def _reanchor(convs: list[Conversation], end_ms: int) -> list[Conversation]:
        latest = max(
            (u.ts_ms for c in convs for u in c.utterances),
            default=max((c.end_ms for c in convs), default=end_ms),
        )
        shift = end_ms - latest
        for c in convs:
            c.start_ms += shift
            c.end_ms += shift
            for u in c.utterances:
                u.ts_ms += shift
        return convs
