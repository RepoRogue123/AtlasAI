"""Atlas API: runs, live event stream, human-in-the-loop responses, skills, sandbox control, evals.

Run:  python -m app.main      (starts the sandbox suite too, if it is not already running)
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

if sys.platform == "win32":  # Playwright needs subprocess support -> Proactor loop on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from agent.events import EventBus
from agent.kernel import AgentRun
from agent.store import Store
from evals import runner as eval_runner
from sandbox import launcher
from tools.browser import MANAGER

store = Store()
bus = EventBus(store)
RUNS: dict[str, AgentRun] = {}
TASKS: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.mark_orphaned_runs()
    await asyncio.to_thread(launcher.ensure_running)
    yield
    for run in RUNS.values():
        run.cancel()
    await MANAGER.shutdown()


app = FastAPI(title="Atlas - Autonomous AI Task Worker", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ----------------------------------------------------------------------------- runs
class RunRequest(BaseModel):
    goal: str
    autonomy: str = "balanced"
    use_skills: bool = True


class HumanResponse(BaseModel):
    request_id: str
    decision: str = "approve"          # approve | reject | edit | answer
    reason: str | None = None
    answer: str | None = None
    args: dict[str, Any] | None = None


@app.post("/api/runs")
async def create_run(req: RunRequest):
    if not req.goal.strip():
        raise HTTPException(400, "goal is required")
    run_id = uuid.uuid4().hex[:12]
    store.create_run(run_id, req.goal.strip(), req.autonomy)
    run = AgentRun(run_id, req.goal, store, bus, autonomy=req.autonomy, use_skills=req.use_skills)
    RUNS[run_id] = run
    TASKS[run_id] = asyncio.create_task(run.execute())
    return {"run_id": run_id}


@app.get("/api/runs")
def list_runs():
    return store.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {**run, "events": store.events(run_id)}


@app.post("/api/runs/{run_id}/respond")
def respond(run_id: str, resp: HumanResponse):
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(404, "run not active")
    payload = resp.model_dump(exclude_none=True)
    payload.pop("request_id")
    if not run.human.resolve(resp.request_id, payload):
        raise HTTPException(409, "request already resolved or unknown")
    return {"ok": True}


@app.post("/api/runs/{run_id}/cancel")
def cancel(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(404, "run not active")
    run.cancel()
    return {"ok": True}


@app.get("/api/runs/{run_id}/shots/{name}")
def screenshot(run_id: str, name: str):
    path = config.RUNS_DIR / Path(run_id).name / Path(name).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


@app.websocket("/ws/runs/{run_id}")
async def run_stream(ws: WebSocket, run_id: str):
    await ws.accept()
    queue = bus.subscribe(run_id)
    try:
        last = 0
        for event in store.events(run_id):           # backlog first, then live
            await ws.send_text(json.dumps(event, default=str))
            last = event["seq"]
        while True:
            event = await queue.get()
            if event["seq"] > last:
                await ws.send_text(json.dumps(event, default=str))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe(run_id, queue)


# ----------------------------------------------------------------------------- skills
@app.get("/api/skills")
def list_skills():
    return store.skills()


@app.delete("/api/skills/{skill_id}")
def delete_skill(skill_id: int):
    store.delete_skill(skill_id)
    return {"ok": True}


# ----------------------------------------------------------------------------- sandbox control
async def _sandbox(method: str, path: str, **kw) -> Any:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.request(method, f"{config.SANDBOX_URL}{path}", **kw)
        r.raise_for_status()
        return r.json()


@app.get("/api/sandbox/chaos")
async def get_chaos():
    return await _sandbox("GET", "/admin/chaos")


class ChaosRequest(BaseModel):
    level: float


@app.post("/api/sandbox/chaos")
async def set_chaos(req: ChaosRequest):
    return await _sandbox("POST", "/admin/chaos", json={"level": max(0.0, min(1.0, req.level))})


@app.post("/api/sandbox/reset")
async def reset_sandbox():
    return await _sandbox("POST", "/admin/reset")


@app.get("/api/sandbox/state")
async def sandbox_state():
    return await _sandbox("GET", "/admin/state")


# ----------------------------------------------------------------------------- meta + evals
@app.get("/api/health")
async def health():
    model = None
    fallbacks = [name for name, key in (("groq", config.GROQ_API_KEY), ("openrouter", config.OPENROUTER_API_KEY)) if key]
    if config.GEMINI_API_KEY or fallbacks:
        try:
            from agent.llm import LLM
            model = await LLM().label()
        except Exception as e:  # noqa: BLE001
            model = f"error: {e}"
    return {"ok": True, "gemini_key": bool(config.GEMINI_API_KEY), "llm_ready": bool(config.GEMINI_API_KEY or fallbacks),
            "model": model, "fallbacks": fallbacks, "sandbox": launcher.is_up(), "sandbox_url": config.SANDBOX_URL}


@app.get("/api/examples")
def examples():
    return [{"id": t["id"], "title": t["title"], "goal": t["goal"], "tags": t.get("tags", [])}
            for t in eval_runner.load_tasks()]


class EvalRequest(BaseModel):
    chaos: float = 0.0
    tasks: list[str] | None = None


@app.get("/api/evals")
def list_evals():
    return eval_runner.list_reports()


@app.get("/api/evals/status")
def eval_status():
    return eval_runner.STATUS


@app.post("/api/evals/run")
async def run_evals(req: EvalRequest):
    if eval_runner.STATUS.get("running"):
        raise HTTPException(409, "an eval suite is already running")
    asyncio.create_task(eval_runner.run_suite(store, bus, chaos=req.chaos, task_ids=req.tasks))
    return {"ok": True}


# ----------------------------------------------------------------------------- built frontend (optional)
DIST = config.PROJECT_DIR / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=config.API_PORT, log_level="info")
