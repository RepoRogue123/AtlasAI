"""Vision fallback: when the text snapshot is not enough (charts, images, canvas, visual layout, unlabeled icons),
the agent can ask a multimodal model about a screenshot of the current page."""
from __future__ import annotations

from typing import TYPE_CHECKING

from tools.registry import ToolResult, tool

if TYPE_CHECKING:
    from agent.context import ToolContext


@tool("look_at_screen", "Ask a vision model a question about a screenshot of the current page. Use only when the "
      "text observation is insufficient (images, charts, visual layout, unlabeled icons, rendering problems).",
      {"question": {"type": "string"}}, ["question"], verifier=True)
async def look_at_screen(ctx: "ToolContext", question: str) -> ToolResult:
    if ctx.llm is None:
        return ToolResult(False, "Vision model unavailable.", error_kind="unknown")
    image = await ctx.browser.page.screenshot(type="jpeg", quality=75)
    await ctx.capture("vision")
    answer = await ctx.llm.vision(image, question)
    return ToolResult(True, f"Vision answer: {answer}", {"url": ctx.browser.page.url}, untrusted=True)
