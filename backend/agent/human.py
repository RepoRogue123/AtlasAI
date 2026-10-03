"""Human-in-the-loop channel: approvals and clarification questions.

The kernel awaits a Future; the API resolves it when the operator clicks Approve / Reject / answers in the UI.
Evals plug in an automatic responder so the same code path runs unattended.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Awaitable, Callable

Emit = Callable[[str, dict], Awaitable[None]]
AutoResponder = Callable[[str, dict], Awaitable[dict]]


class HumanChannel:
    def __init__(self, emit: Emit, auto: AutoResponder | None = None, timeout_s: float = 1800) -> None:
        self._emit = emit
        self._auto = auto
        self._timeout = timeout_s
        self.pending: dict[str, asyncio.Future] = {}

    async def request(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        """kind: 'approval' | 'question'. Returns the operator's response dict."""
        request_id = uuid.uuid4().hex[:10]
        await self._emit(f"{kind}_requested", {**payload, "request_id": request_id})
        if self._auto:
            response = await self._auto(kind, payload)
        else:
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            self.pending[request_id] = fut
            try:
                response = await asyncio.wait_for(fut, self._timeout)
            except asyncio.TimeoutError:
                response = {"decision": "reject", "reason": "No response from operator (timed out)."}
            finally:
                self.pending.pop(request_id, None)
        await self._emit(f"{kind}_resolved", {"request_id": request_id, **response})
        return response

    def resolve(self, request_id: str, response: dict[str, Any]) -> bool:
        fut = self.pending.get(request_id)
        if not fut or fut.done():
            return False
        fut.set_result(response)
        return True

    def cancel_all(self) -> None:
        for fut in self.pending.values():
            if not fut.done():
                fut.set_result({"decision": "reject", "reason": "Run cancelled."})
