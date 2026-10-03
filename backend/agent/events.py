"""Typed event stream. Every agent step is an event: persisted (replay, audit) and fanned out to WebSocket clients.

Event types: run_started, plan, thought, action, observation, screenshot, memory, document, search, http, file,
approval_requested/resolved, question_requested/resolved, recovery, security, verification_started,
verifier_action, verification, skill_used, skill_learned, usage, error, run_finished.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

from agent.store import Store


class EventBus:
    def __init__(self, store: Store) -> None:
        self.store = store
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._seq: dict[str, int] = defaultdict(int)

    async def publish(self, run_id: str, type_: str, data: dict[str, Any]) -> dict[str, Any]:
        self._seq[run_id] += 1
        event = {"run_id": run_id, "seq": self._seq[run_id], "ts": time.time(), "type": type_, "data": data}
        self.store.add_event(event)
        for q in list(self._subs[run_id]):
            q.put_nowait(event)
        return event

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[run_id].add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        self._subs[run_id].discard(q)
