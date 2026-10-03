"""Per-run state shared between the kernel and the tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent.human import HumanChannel
from agent.memory import WorkingMemory
from agent.security import SecurityMonitor
from agent.vault import Vault
from tools.browser import BrowserSession

Emit = Callable[[str, dict], Awaitable[None]]


@dataclass
class Plan:
    understanding: str = ""
    steps: list[dict[str, str]] = field(default_factory=list)       # {title, status}
    success_criteria: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    version: int = 0

    def render(self) -> str:
        icon = {"done": "[x]", "in_progress": "[>]", "failed": "[!]", "skipped": "[-]"}
        lines = [f"{i + 1}. {icon.get(s.get('status', ''), '[ ]')} {s['title']}" for i, s in enumerate(self.steps)]
        crit = "\n".join(f"- {c}" for c in self.success_criteria) or "- (none)"
        return "\n".join(lines) + f"\nSuccess criteria:\n{crit}"

    def as_dict(self) -> dict[str, Any]:
        return {"understanding": self.understanding, "steps": self.steps, "success_criteria": self.success_criteria,
                "assumptions": self.assumptions, "ambiguities": self.ambiguities, "version": self.version}


@dataclass
class ToolContext:
    run_id: str
    goal: str
    browser: BrowserSession
    memory: WorkingMemory
    vault: Vault
    human: HumanChannel
    security: SecurityMonitor
    emit: Emit
    plan: Plan
    step: int = 0
    verifier_mode: bool = False
    finish_payload: dict[str, Any] | None = None
    last_screenshot: str | None = None
    llm: Any = None    # set by the kernel; used by tools that need a model (vision)

    def shot_url(self, name: str) -> str:
        return f"/api/runs/{self.run_id}/shots/{name}" if name else ""

    async def capture(self, tag: str, highlight_ref: int | None = None, extra: dict | None = None) -> str:
        name = (await self.browser.highlight_shot(highlight_ref, tag) if highlight_ref is not None
                else await self.browser.screenshot(tag))
        if name:
            self.last_screenshot = self.shot_url(name)
            await self.emit("screenshot", {"url": self.last_screenshot, "page_url": self.browser.page.url,
                                           "tag": tag, "step": self.step, "actor": "verifier" if self.verifier_mode else "agent",
                                           **(extra or {})})
        return self.last_screenshot or ""
