"""Start the sandbox suite in a background thread if it is not already running (one-command dev experience)."""
from __future__ import annotations

import threading
import time

import httpx
import uvicorn

from config import SANDBOX_HOST, SANDBOX_PORT, SANDBOX_URL


def is_up() -> bool:
    try:
        return httpx.get(f"{SANDBOX_URL}/admin/chaos", timeout=1.5).status_code == 200
    except httpx.HTTPError:
        return False


def ensure_running(timeout: float = 15) -> bool:
    if is_up():
        return True
    from sandbox.app import app

    server = uvicorn.Server(uvicorn.Config(app, host=SANDBOX_HOST, port=SANDBOX_PORT, log_level="warning"))
    threading.Thread(target=server.run, name="sandbox", daemon=True).start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_up():
            return True
        time.sleep(0.25)
    return False
