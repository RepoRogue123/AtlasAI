"""Cognitive tools: memory, plan management, talking to the human, finishing."""
from __future__ import annotations

from typing import TYPE_CHECKING

from tools.registry import ToolResult, tool

if TYPE_CHECKING:
    from agent.context import ToolContext

STATUSES = ["pending", "in_progress", "done", "skipped", "failed"]


@tool("remember", "Store an important fact you discovered (value + where it came from) so you and the final report "
      "can rely on it. Use for every value you will later enter, compare or report.",
      {"key": {"type": "string", "description": "Short name, e.g. 'invoice_amount'"},
       "value": {"type": "string"},
       "source": {"type": "string", "description": "Where you saw it, e.g. 'Acme_INV-2041.pdf' or a URL"}},
      ["key", "value", "source"])
async def remember(ctx: "ToolContext", key: str, value: str, source: str) -> ToolResult:
    fact = ctx.memory.remember(key, value, source, ctx.step, ctx.last_screenshot)
    await ctx.emit("memory", {"key": fact.key, "value": fact.value, "source": fact.source, "step": fact.step,
                              "screenshot": fact.screenshot})
    return ToolResult(True, f"Remembered {fact.key} = {fact.value}")


@tool("update_plan", "Update the plan: mark progress and/or revise steps when reality differs from the plan.",
      {"steps": {"type": "array", "items": {"type": "object", "properties": {
          "title": {"type": "string"}, "status": {"type": "string", "enum": STATUSES}},
          "required": ["title", "status"]}}},
      ["steps"])
async def update_plan(ctx: "ToolContext", steps: list[dict]) -> ToolResult:
    old_titles = [s["title"] for s in ctx.plan.steps]
    ctx.plan.steps = [{"title": s["title"], "status": s.get("status", "pending")} for s in steps]
    replanned = [s["title"] for s in ctx.plan.steps] != old_titles
    if replanned:
        ctx.plan.version += 1
    await ctx.emit("plan", {**ctx.plan.as_dict(), "replanned": replanned})
    return ToolResult(True, "Plan updated." + (" (revised)" if replanned else ""))


@tool("ask_user", "Ask the user a clarifying question when the request is ambiguous, information is missing, or you "
      "cannot safely proceed. Blocks until answered. Prefer finding information yourself first.",
      {"question": {"type": "string"},
       "options": {"type": "array", "items": {"type": "string"}, "description": "Optional suggested answers"}},
      ["question"])
async def ask_user(ctx: "ToolContext", question: str, options: list[str] | None = None) -> ToolResult:
    resp = await ctx.human.request("question", {"question": question, "options": options or [], "step": ctx.step})
    answer = resp.get("answer") or resp.get("reason") or "(no answer)"
    return ToolResult(True, f"User answered: {answer}", {"answer": answer})


@tool("finish", "End the task. Call ONLY after you have checked the outcome yourself. An independent verifier will "
      "then check your claims against the real systems.",
      {"outcome": {"type": "string", "enum": ["success", "partial", "failed", "blocked"]},
       "summary": {"type": "string", "description": "2-4 sentences for the user: what was done, what was not."},
       "results": {"type": "array", "description": "Key outputs, e.g. extracted values or created record ids",
                   "items": {"type": "object", "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
                             "required": ["label", "value"]}},
       "evidence": {"type": "array", "items": {"type": "string"},
                    "description": "Where the outcome can be checked: URLs, record ids, document names"}},
      ["outcome", "summary"])
async def finish(ctx: "ToolContext", outcome: str, summary: str, results: list[dict] | None = None,
                 evidence: list[str] | None = None) -> ToolResult:
    ctx.finish_payload = {"outcome": outcome, "summary": summary, "results": results or [], "evidence": evidence or []}
    return ToolResult(True, "Finish requested.")
