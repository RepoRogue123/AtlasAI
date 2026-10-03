"""Chaos Mode: probabilistic fault injection for the sandbox, so the agent's recovery logic is exercised
by real failures rather than mocked ones.

Faults (chosen per request with probability = chaos level):
  * error503   - server returns 503 before doing any work (safe to retry)
  * latency    - 1.5-3.5s delay
  * consent    - a blocking cookie-consent modal is rendered over the page (GET html only)
  * session    - vendor-portal session silently expires (portal pages only)
"""
from __future__ import annotations

import asyncio
import random
import time
from collections import deque

from fastapi import Request
from fastapi.responses import HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware

from sandbox import db

EXEMPT_PREFIXES = ("/admin", "/favicon", "/static")
LOG: deque[dict] = deque(maxlen=200)
_rng = random.Random()


def seed(value: int | None) -> None:
    _rng.seed(value)


def level() -> float:
    try:
        return max(0.0, min(1.0, float(db.get_setting("chaos_level", "0"))))
    except ValueError:
        return 0.0


def _pick_fault(request: Request) -> str:
    is_get = request.method == "GET"
    portal = request.url.path.startswith("/portal") and request.url.path != "/portal/login"
    options = [("error503", 0.35), ("latency", 0.25)]
    if is_get:
        options.append(("consent", 0.25))
    if is_get and portal:
        options.append(("session", 0.15))
    r = _rng.random() * sum(w for _, w in options)
    for name, w in options:
        r -= w
        if r <= 0:
            return name
    return options[-1][0]


ERROR_PAGE = """<!doctype html><html><head><title>503 Service Unavailable</title></head>
<body style="font-family:sans-serif;padding:40px"><h1>503 - Service temporarily unavailable</h1>
<p>The server is overloaded or down for maintenance. Please try again in a moment.</p></body></html>"""


class ChaosMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        lvl = level()
        if lvl <= 0 or path.startswith(EXEMPT_PREFIXES) or _rng.random() >= lvl:
            return await call_next(request)
        fault = _pick_fault(request)
        LOG.append({"ts": time.time(), "fault": fault, "method": request.method, "path": path})
        if fault == "error503":
            return HTMLResponse(ERROR_PAGE, status_code=503)
        if fault == "latency":
            await asyncio.sleep(_rng.uniform(1.5, 3.5))
        elif fault == "consent":
            request.state.chaos_modal = True
        elif fault == "session":
            request.state.chaos_expire_session = True
        return await call_next(request)
