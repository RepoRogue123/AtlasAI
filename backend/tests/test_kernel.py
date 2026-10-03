"""Kernel end-to-end with a scripted LLM: exercises planning, dispatch, the approval gate, injection blocking,
recovery, the verifier hand-off and the final report - deterministically and without network access to Gemini."""
import re

import httpx
import pytest
from google.genai import types

import config
from agent import kernel as kernel_mod
from agent import verifier as verifier_mod
from agent.events import EventBus
from agent.llm import FunctionCall, Reply, Usage
from agent.store import Store
from sandbox import launcher
from sandbox.seed import EXPECTED
from tools.browser import MANAGER


class ScriptedLLM:
    """Plays back tool calls. Each script item is a function of the latest observation text -> (name, args)."""

    def __init__(self, agent_script, verifier_script):
        self.usage = Usage()
        self.agent_script = list(agent_script)
        self.verifier_script = list(verifier_script)
        self.last_obs = ""

    fallbacks: list = []

    async def model(self, preferred=None):
        return "scripted"

    async def label(self):
        return "scripted"

    async def json(self, system, prompt, schema, model=None):
        if "reusable skill" in system:
            return {"name": "enter_invoice", "summary": "s", "applies_when": "invoice", "procedure": ["a"],
                    "pitfalls": [], "keywords": ["invoice"]}
        return {"understanding": "enter invoice", "steps": ["find", "enter"], "success_criteria": ["bill exists"],
                "assumptions": [], "ambiguities": []}

    async def act(self, system, contents, tools, model=None, thinking=True):
        last = contents[-1]
        for part in last.parts or []:
            if part.function_response:
                self.last_obs = str(part.function_response.response.get("result", ""))
        is_verifier = any(t["name"] == "submit_verdict" for t in tools)
        script = self.verifier_script if is_verifier else self.agent_script
        name, args = script.pop(0)(self.last_obs)
        args = {**args, "rationale": "scripted"}
        content = types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))])
        return Reply(content=content, thoughts=["thinking..."], calls=[FunctionCall(name, args)])


def ref(label):
    def find(obs):
        m = re.search(r"\[(\d+)\] [^\n]*" + re.escape(label), obs)
        assert m, f"{label!r} not in observation:\n{obs[:1500]}"
        return int(m.group(1))
    return find


S = lambda: config.SANDBOX_URL  # noqa: E731


@pytest.fixture()
def env(monkeypatch):
    assert launcher.ensure_running()
    httpx.post(f"{S()}/admin/reset")
    httpx.post(f"{S()}/admin/chaos", json={"level": 0})
    store = Store()
    return store, EventBus(store)


async def run_with(monkeypatch, env, agent_script, verifier_script, autonomy="balanced", decisions=None):
    llm = ScriptedLLM(agent_script, verifier_script)
    monkeypatch.setattr(kernel_mod, "LLM", lambda *a, **k: llm)
    decisions = list(decisions or [])

    async def auto(kind, payload):
        return decisions.pop(0) if decisions else {"decision": "approve"}

    store, bus = env
    run_id = f"k-{len(store.list_runs())}"
    store.create_run(run_id, "Enter the latest Acme invoice", autonomy)
    run = kernel_mod.AgentRun(run_id, "Enter the latest Acme invoice", store, bus, autonomy=autonomy,
                              auto_responder=auto, use_skills=False)
    report = await run.execute()
    await MANAGER.shutdown()
    return report, store.events(run_id)


DUE = EXPECTED["acme_latest"]["due_date"]


def bill_form_script(invoice="INV-2041", amount="4820.50", due=None):
    return [
        lambda o: ("read_document", {"url": f"{S()}/mail/attachments/Acme_INV-2041.pdf"}),   # the source
        lambda o: ("browser_goto", {"url": f"{S()}/erp/bills/new"}),
        lambda o: ("browser_select", {"ref": ref('select "Vendor"')(o), "option": "Acme Supplies"}),
        lambda o: ("browser_observe", {}),
        lambda o: ("browser_type", {"ref": ref('"Vendor invoice number"')(o), "text": invoice}),
        lambda o: ("browser_observe", {}),
        lambda o: ("browser_type", {"ref": ref('"Amount"')(o), "text": amount}),
        lambda o: ("browser_observe", {}),
        lambda o: ("browser_type", {"ref": ref('"Due date"')(o), "text": due or DUE}),
        lambda o: ("browser_observe", {}),
        lambda o: ("browser_click", {"ref": ref('button "Submit bill"')(o)}),
    ]


async def test_full_run_with_approval_and_verification(monkeypatch, env):
    agent = bill_form_script() + [
        lambda o: ("remember", {"key": "bill", "value": "created", "source": "erp"}),
        lambda o: ("finish", {"outcome": "success", "summary": "Entered INV-2041.", "results": [], "evidence": []}),
    ]
    verifier = [
        lambda o: ("browser_goto", {"url": f"{S()}/erp/bills"}),
        lambda o: ("submit_verdict", {"verdict": "verified" if "INV-2041" in o else "not_verified",
                                      "criteria": [{"criterion": "bill exists", "passed": True, "evidence": "list"}],
                                      "notes": ""}),
    ]
    report, events = await run_with(monkeypatch, env, agent, verifier)
    types_ = [e["type"] for e in events]
    assert report["status"] == "success", report
    assert "approval_requested" in types_                      # Submit bill carries an amount -> critical
    assert "verification" in types_ and "skill_learned" in types_
    assert any(e["type"] == "screenshot" for e in events)


async def test_rejected_approval_reaches_the_agent(monkeypatch, env):
    agent = bill_form_script() + [
        lambda o: ("finish", {"outcome": "blocked", "summary": "Operator rejected." if "REJECTED" in o else "??"}),
    ]
    report, events = await run_with(monkeypatch, env, agent, [], decisions=[{"decision": "reject", "reason": "wrong vendor"}])
    assert report["status"] == "blocked" and report["summary"] == "Operator rejected."
    state = httpx.get(f"{S()}/admin/state").json()
    assert not [b for b in state["bills"] if b["invoice_number"] == "INV-2041"]


async def test_injected_value_is_blocked(monkeypatch, env):
    agent = [
        lambda o: ("browser_goto", {"url": f"{S()}/mail/message/6"}),           # the injection email
        lambda o: ("browser_goto", {"url": f"{S()}/erp/bills/new"}),
        lambda o: ("browser_type", {"ref": ref('"Vendor invoice number"')(o), "text": "INV-9999"}),
        lambda o: ("finish", {"outcome": "failed", "summary": "blocked" if "BLOCKED" in o else "not blocked"}),
    ]
    report, events = await run_with(monkeypatch, env, agent, [], autonomy="autonomous")
    kinds = [e["data"].get("kind") for e in events if e["type"] == "security"]
    assert "injection_detected" in kinds and "blocked" in kinds
    assert report["summary"] == "blocked"


async def test_ungrounded_amount_is_bounced_then_escalated(monkeypatch, env):
    """Typing 4802.50 when the invoice says 4,820.50: first submit is refused, insisting forces a human decision."""
    agent = bill_form_script(amount="4802.50") + [
        lambda o: ("browser_observe", {}),
        lambda o: ("browser_click", {"ref": ref('button "Submit bill"')(o)}),       # insists
        lambda o: ("finish", {"outcome": "blocked", "summary": "rejected" if "REJECTED" in o else "?"}),
    ]
    report, events = await run_with(monkeypatch, env, agent, [], autonomy="autonomous",
                                    decisions=[{"decision": "reject", "reason": "amount is wrong"}])
    grounding = [e for e in events if e["type"] == "recovery" and e["data"]["kind"] == "grounding"]
    approvals = [e for e in events if e["type"] == "approval_requested"]
    assert grounding and "4802.50" in grounding[0]["data"]["strategy"]
    assert approvals and approvals[0]["data"]["ungrounded"] == ["4802.50"]   # escalated even in autonomous mode
    assert report["summary"] == "rejected"
    state = httpx.get(f"{S()}/admin/state").json()
    assert not [b for b in state["bills"] if b["invoice_number"] == "INV-2041"]


async def test_failed_verification_feeds_back_then_fails_honestly(monkeypatch, env):
    agent = [
        lambda o: ("finish", {"outcome": "success", "summary": "Done (but did nothing)."}),
        lambda o: ("finish", {"outcome": "success", "summary": "Done again." if "verification FAILED" in o else "?"}),
    ]
    nope = lambda o: ("submit_verdict", {"verdict": "not_verified", "notes": "no bill",  # noqa: E731
                                         "criteria": [{"criterion": "bill exists", "passed": False, "evidence": "absent"}]})
    report, events = await run_with(monkeypatch, env, agent, [nope, nope])
    assert report["status"] == "failed_verification"
    assert sum(1 for e in events if e["type"] == "verification") == 2


async def test_verifier_outage_degrades_to_unverified(monkeypatch, env):
    """If no LLM can run the verifier, a finished task is reported 'unverified', not discarded as a crash."""
    from agent.llm import LLMError

    async def verifier_down(*a, **k):
        raise LLMError("Gemini and all fallback providers are unavailable")
    monkeypatch.setattr(kernel_mod.verifier, "verify", verifier_down)
    agent = [lambda o: ("finish", {"outcome": "success", "summary": "Done."})]
    report, events = await run_with(monkeypatch, env, agent, [])
    assert report["status"] == "unverified"
    assert "Verifier could not run" in report["verification"]["notes"]
