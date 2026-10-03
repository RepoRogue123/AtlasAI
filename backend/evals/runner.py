"""Eval runner: reset sandbox -> run task -> check ground truth. Produces a JSON report with success rate,
steps, retries, tokens, cost and time, optionally under Chaos Mode.

CLI:  python -m evals.runner --chaos 0.3 --tasks invoice_email,portal_invoice
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import yaml

import config
from evals.checkers import CHECKS

TASKS_FILE = Path(__file__).parent / "tasks.yaml"
REPORTS_DIR = config.DATA_DIR / "evals"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
STATUS: dict[str, Any] = {"running": False}


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_FILE.read_text(encoding="utf-8"))


def list_reports() -> list[dict]:
    reports = []
    for p in sorted(REPORTS_DIR.glob("*.json"), reverse=True):
        try:
            reports.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return reports


async def _admin(method: str, path: str, **kw) -> Any:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.request(method, f"{config.SANDBOX_URL}{path}", **kw)
        r.raise_for_status()
        return r.json()


async def run_task(task: dict, store, bus, chaos: float, seed: int, use_skills: bool) -> dict:
    from agent.kernel import AgentRun

    await _admin("POST", "/admin/reset")
    await _admin("POST", "/admin/chaos", json={"level": chaos, "seed": seed})

    async def auto(kind: str, payload: dict) -> dict:
        if kind == "approval":
            return {"decision": "approve", "reason": "auto-approved (eval)"}
        return {"decision": "answer", "answer": task.get("answer", "Use your best judgement.")}

    run_id = f"eval-{task['id']}-{uuid.uuid4().hex[:6]}"
    store.create_run(run_id, task["goal"], "balanced", source="eval")
    run = AgentRun(run_id, task["goal"], store, bus, autonomy="balanced", auto_responder=auto, use_skills=use_skills)
    report = await run.execute()
    await _admin("POST", "/admin/chaos", json={"level": 0})
    state = await _admin("GET", "/admin/state")
    events = store.events(run_id)
    passed, detail = CHECKS[task["check"]](state, report, events)
    return {
        "id": task["id"], "title": task["title"], "run_id": run_id, "passed": passed, "detail": detail,
        "agent_status": report.get("status"), "verifier": (report.get("verification") or {}).get("verdict"),
        "steps": report.get("steps"), "retries": report.get("retries"), "failures": report.get("failures"),
        "cost_usd": report.get("usage", {}).get("cost_usd", 0), "tokens": report.get("usage", {}).get("input_tokens", 0)
        + report.get("usage", {}).get("output_tokens", 0), "duration_s": report.get("duration_s"),
        "injections_detected": sum(1 for e in events if e["type"] == "security" and e["data"].get("kind") == "injection_detected"),
        "recoveries": sum(1 for e in events if e["type"] == "recovery"),
    }


async def run_suite(store, bus, chaos: float = 0.0, task_ids: list[str] | None = None, use_skills: bool = False,
                    seed: int = 42) -> dict:
    tasks = [t for t in load_tasks() if not task_ids or t["id"] in task_ids]
    STATUS.update(running=True, total=len(tasks), done=0, current=None, chaos=chaos)
    results, started = [], time.time()
    try:
        for task in tasks:
            STATUS["current"] = task["id"]
            try:
                results.append(await run_task(task, store, bus, chaos, seed, use_skills))
            except Exception as e:  # noqa: BLE001 - one broken task must not kill the suite
                results.append({"id": task["id"], "title": task["title"], "passed": False, "detail": f"crash: {e}"})
            STATUS["done"] += 1
        # Verifier agreement: how often the agent's independent verifier agreed with ground truth.
        judged = [r for r in results if r.get("verifier") in ("verified", "not_verified")]
        agree = sum(1 for r in judged if (r["verifier"] == "verified") == r["passed"])
        report = {
            "id": time.strftime("%Y%m%d-%H%M%S"), "created_at": time.time(), "chaos": chaos, "model": config.GEMINI_MODEL,
            "tasks": results, "passed": sum(r["passed"] for r in results), "total": len(results),
            "success_rate": round(sum(r["passed"] for r in results) / max(1, len(results)), 3),
            "verifier_agreement": round(agree / len(judged), 3) if judged else None,
            "avg_steps": round(sum(r.get("steps") or 0 for r in results) / max(1, len(results)), 1),
            "total_cost_usd": round(sum(r.get("cost_usd") or 0 for r in results), 4),
            "duration_s": round(time.time() - started, 1),
        }
        (REPORTS_DIR / f"{report['id']}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        STATUS.update(running=False, current=None)


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    parser = argparse.ArgumentParser(description="Run the Atlas evaluation suite")
    parser.add_argument("--chaos", type=float, default=0.0)
    parser.add_argument("--tasks", type=str, default="")
    parser.add_argument("--skills", action="store_true", help="allow skill-library reuse between tasks")
    args = parser.parse_args()

    from agent.events import EventBus
    from agent.store import Store
    from sandbox import launcher
    from tools.browser import MANAGER

    if not launcher.ensure_running():
        sys.exit("Sandbox did not start")
    store = Store()
    bus = EventBus(store)

    async def go():
        try:
            return await run_suite(store, bus, args.chaos, [t for t in args.tasks.split(",") if t] or None, args.skills)
        finally:
            await MANAGER.shutdown()

    report = asyncio.run(go())
    for r in report["tasks"]:
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['id']:<20} steps={r.get('steps')} retries={r.get('retries')} "
              f"verifier={r.get('verifier')}  {r['detail']}")
    print(f"\nSuccess {report['passed']}/{report['total']} ({report['success_rate']:.0%}) | chaos={report['chaos']} | "
          f"verifier agreement={report['verifier_agreement']} | cost=${report['total_cost_usd']}")


if __name__ == "__main__":
    main()
