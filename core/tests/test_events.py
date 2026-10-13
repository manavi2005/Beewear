"""Tests for the SSE pub/sub broker (ADR-025)."""

from __future__ import annotations

import asyncio

from attune.events import Broker


async def test_broker_delivers_to_subscriber():
    b = Broker()
    queue = await b.subscribe()
    b.publish("vitals", {"latest_bpm": 88})
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["type"] == "vitals"
    assert event["data"]["latest_bpm"] == 88


async def test_broker_broadcasts_to_all_subscribers():
    b = Broker()
    q1 = await b.subscribe()
    q2 = await b.subscribe()
    b.publish("checkin", {"value": 4})
    e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert e1["data"]["value"] == 4 and e2["data"]["value"] == 4


def test_publish_without_subscribers_is_noop():
    b = Broker()
    b.publish("vitals", {"x": 1})  # no loop registered yet — must not raise
    assert b.subscriber_count == 0
