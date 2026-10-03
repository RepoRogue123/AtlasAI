"""Action risk assessment and the human-approval gate.

Risk is decided by the runtime, not by the model:
  read     - navigation, observation, typing into a field (nothing committed)
  write    - submits a state-changing form (POST), writes a file
  critical - irreversible or financial: payments, sending email, deletes, any form carrying an amount
Autonomy mode decides which risk levels need the operator's approval.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.context import ToolContext
    from tools.registry import ToolSpec

CRITICAL_RE = re.compile(r"\b(pay|paid|payment|send|delete|remove|transfer|wire|purchase|refund)\b", re.I)
FINANCIAL_FIELD_RE = re.compile(r"\b(amount|total|price|payment|iban|account number)\b", re.I)

APPROVAL_LEVELS: dict[str, set[str]] = {
    "supervised": {"write", "critical"},
    "balanced": {"critical"},
    "autonomous": set(),
}
RANK = {"read": 0, "write": 1, "critical": 2}


@dataclass
class Assessment:
    risk: str
    reason: str
    target: str = ""
    form_fields: list[dict[str, str]] = field(default_factory=list)

    def needs_approval(self, autonomy: str) -> bool:
        return self.risk in APPROVAL_LEVELS.get(autonomy, APPROVAL_LEVELS["balanced"])


def _form_risk(info: dict[str, Any]) -> Assessment:
    label = info.get("text", "")
    fields = info.get("fields") or []
    if info.get("form_method") != "post":
        return Assessment("read", "GET form / non-submitting control", label, fields)
    if info.get("form_has_password"):
        return Assessment("read", "sign-in form (credentials injected from vault)", label, fields)
    if CRITICAL_RE.search(label):
        return Assessment("critical", f"irreversible action: '{label}'", label, fields)
    if any(FINANCIAL_FIELD_RE.search(f.get("label", "")) for f in fields):
        return Assessment("critical", "submits a record with financial impact", label, fields)
    return Assessment("write", f"submits a state-changing form: '{label}'", label, fields)


async def assess(spec: "ToolSpec", args: dict[str, Any], ctx: "ToolContext") -> Assessment:
    if spec.name == "browser_click":
        info = await ctx.browser.element_info(args.get("ref", -1))
        if not info:
            return Assessment("read", "unknown element (will fail and re-observe)")
        if info["tag"] == "A":
            return Assessment("read", "follows a link", info.get("text", ""))
        if info["tag"] in ("BUTTON", "INPUT") and info.get("submit_like"):
            return _form_risk(info)
        if CRITICAL_RE.search(info.get("text", "")):
            return Assessment("critical", f"control labelled '{info['text']}'", info["text"])
        return Assessment("read", "non-submitting control", info.get("text", ""))
    if spec.name == "browser_type" and args.get("submit"):
        info = await ctx.browser.element_info(args.get("ref", -1))
        if info:
            return _form_risk(info)
    return Assessment(spec.risk, f"tool default risk ({spec.risk})")


def action_text(spec_name: str, args: dict[str, Any], assessment: Assessment) -> str:
    """Everything an action would write - used for taint checks."""
    parts = [str(args.get(k, "")) for k in ("text", "option", "content", "value")]
    parts += [f.get("value", "") for f in assessment.form_fields]
    return " ".join(p for p in parts if p)
