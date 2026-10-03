"""Integration: real Chromium driving the real sandbox through the tool layer (no LLM involved)."""
import re

import httpx
import pytest

import config
from agent.context import Plan, ToolContext
from agent.human import HumanChannel
from agent.memory import WorkingMemory
from agent.security import SecurityMonitor
from agent.vault import Vault
from sandbox import launcher
from tools.browser import MANAGER
from tools.registry import REGISTRY, load_all


def ref_for(text: str, label: str) -> int:
    m = re.search(r"\[(\d+)\] [^\n]*" + re.escape(label), text)
    assert m, f"no element matching {label!r} in:\n{text[:2000]}"
    return int(m.group(1))


@pytest.fixture()
async def ctx(tmp_path):
    assert launcher.ensure_running()
    httpx.post(f"{config.SANDBOX_URL}/admin/reset")
    httpx.post(f"{config.SANDBOX_URL}/admin/chaos", json={"level": 0})
    load_all()
    events = []

    async def emit(t, d):
        events.append((t, d))
    session = await MANAGER.new_session(tmp_path)
    c = ToolContext("t1", "test", session, WorkingMemory(), Vault(), HumanChannel(emit), SecurityMonitor("test"),
                    emit, Plan())
    c.events = events
    yield c
    await session.close()
    await MANAGER.shutdown()


async def call(ctx, name, **args):
    return await REGISTRY[name].handler(ctx, **args)


async def test_read_invoice_pdf_and_enter_bill(ctx):
    r = await call(ctx, "browser_goto", url=f"{config.SANDBOX_URL}/mail")
    assert r.ok and "Invoice INV-2041" in r.output
    r = await call(ctx, "browser_click", ref=ref_for(r.output, "Invoice INV-2041"))
    assert "Acme_INV-2041.pdf" in r.output
    doc = await call(ctx, "browser_click", ref=ref_for(r.output, "Acme_INV-2041.pdf"))
    assert doc.ok and "4,820.50" in doc.output                      # PDF text extracted

    r = await call(ctx, "browser_goto", url=f"{config.SANDBOX_URL}/erp/bills/new")
    await call(ctx, "browser_select", ref=ref_for(r.output, 'select "Vendor"'), option="Acme Supplies")
    await call(ctx, "browser_type", ref=ref_for(r.output, '"Vendor invoice number"'), text="INV-2041")
    await call(ctx, "browser_type", ref=ref_for(r.output, '"Amount"'), text="4820.50")
    await call(ctx, "browser_type", ref=ref_for(r.output, '"Due date"'), text="2030-01-31")
    r = await call(ctx, "browser_click", ref=ref_for(r.output, 'button "Submit bill"'))
    assert r.ok and "created successfully" in r.output
    state = httpx.get(f"{config.SANDBOX_URL}/admin/state").json()
    assert any(b["invoice_number"] == "INV-2041" and b["amount"] == 4820.50 for b in state["bills"])


async def test_portal_login_with_vault_secret_never_exposes_password(ctx):
    r = await call(ctx, "browser_goto", url=f"{config.SANDBOX_URL}/portal")
    await call(ctx, "browser_type", ref=ref_for(r.output, '"Username"'), text="{{secret:globex_portal_username}}")
    r2 = await call(ctx, "browser_type", ref=ref_for(r.output, '"Password"'), text="{{secret:globex_portal_password}}",
                    submit=True)
    assert "GX-5531" in r2.output
    assert ctx.vault.resolve("{{secret:globex_portal_password}}") not in r2.output


async def test_overlay_blocks_click_and_is_reported(ctx):
    httpx.post(f"{config.SANDBOX_URL}/admin/chaos", json={"level": 1.0, "seed": 3})
    saw_modal = False
    for _ in range(15):     # with level 1.0, some loads render the consent modal
        try:
            r = await call(ctx, "browser_goto", url=f"{config.SANDBOX_URL}/helpdesk")
        except Exception:
            continue
        if "modal dialog is open" in r.output:
            saw_modal = True
            break
    httpx.post(f"{config.SANDBOX_URL}/admin/chaos", json={"level": 0})
    assert saw_modal
