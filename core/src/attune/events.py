"""In-process pub/sub for Server-Sent Events (ADR-025).

The dashboard subscribes to ``GET /events`` and receives a push the instant a vital sample or
check-in is ingested — no polling. This broker bridges the two concurrency worlds in FastAPI:

- SSE subscribers live on the asyncio event loop (each gets an ``asyncio.Queue``).
- The ingest endpoints are sync (``def``) and run in a threadpool, so they publish from a
  different thread. ``publish()`` is therefore thread-safe: it hands each queue a
  ``call_soon_threadsafe`` so the item is enqueued on the loop thread.

Single-process only — fine for a local hackathon service; a multi-worker deployment would swap
this for Redis pub/sub behind the same interface.
"""

from __future__ import annotations

import asyncio
from typing import Any


class Broker:
    def __init__(self, max_queue: int = 200):
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._max_queue = max_queue

    async def subscribe(self) -> asyncio.Queue:
        """Register a subscriber from within the event loop (an SSE request)."""
        self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcast an event to all subscribers. Safe to call from any thread."""
        loop = self._loop
        if loop is None or not self._subscribers:
            return
        event = {"type": event_type, "data": data}
        for queue in list(self._subscribers):
            loop.call_soon_threadsafe(self._offer, queue, event)

    @staticmethod
    def _offer(queue: asyncio.Queue, event: dict[str, Any]) -> None:
        """Enqueue without blocking; drop the event if a slow client's queue is full."""
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Module-level singleton shared by the API.
broker = Broker()
