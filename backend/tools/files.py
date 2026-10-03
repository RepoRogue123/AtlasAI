"""Workspace file tools. The agent can only touch files inside data/workspace (path traversal is rejected)."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from config import WORKSPACE_DIR
from tools.registry import ToolResult, tool

if TYPE_CHECKING:
    from agent.context import ToolContext


def _safe(path: str) -> Path:
    p = (WORKSPACE_DIR / path).resolve()
    if WORKSPACE_DIR.resolve() not in p.parents and p != WORKSPACE_DIR.resolve():
        raise PermissionError("Path escapes the workspace")
    return p


@tool("write_file", "Write a text file (report, CSV, notes) into the agent workspace.",
      {"path": {"type": "string", "description": "Relative path, e.g. 'reports/overdue.csv'"},
       "content": {"type": "string"}}, ["path", "content"], risk="write")
async def write_file(ctx: "ToolContext", path: str, content: str) -> ToolResult:
    p = _safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    await ctx.emit("file", {"path": path, "bytes": len(content.encode()), "step": ctx.step})
    return ToolResult(True, f"Wrote {len(content)} chars to workspace/{path}", {"path": path})


@tool("read_file", "Read a text file from the agent workspace.", {"path": {"type": "string"}}, ["path"])
async def read_file(ctx: "ToolContext", path: str) -> ToolResult:
    p = _safe(path)
    if not p.exists():
        return ToolResult(False, f"No such file: {path}", error_kind="element_not_found")
    return ToolResult(True, p.read_text(encoding="utf-8")[:8000])


@tool("list_files", "List files in the agent workspace.")
async def list_files(ctx: "ToolContext") -> ToolResult:
    files = [str(p.relative_to(WORKSPACE_DIR)) for p in WORKSPACE_DIR.rglob("*") if p.is_file()]
    return ToolResult(True, "\n".join(files) or "(workspace is empty)")
