"""Browser tools. Every action returns the *new* page observation, so act -> observe is one step."""
from __future__ import annotations

from typing import TYPE_CHECKING

from tools.browser import DOC_HREF, BrowserSession
from tools.registry import ToolResult, tool

if TYPE_CHECKING:
    from agent.context import ToolContext

REF = {"type": "integer", "description": "Element ref number from the latest page observation, e.g. 12 for [12]."}


async def _observation(ctx: "ToolContext", summary: str, shot_tag: str) -> ToolResult:
    snap = await ctx.browser.observe()
    await ctx.capture(shot_tag)
    text = f"{summary}\n{BrowserSession.render(snap)}"
    data = {"url": snap["url"], "title": snap["title"], "status": snap.get("status")}
    if snap.get("status") and snap["status"] >= 500:
        return ToolResult(False, f"Server error {snap['status']} - the action probably did NOT take effect.\n{text}",
                          data, error_kind="transient", untrusted=True)
    return ToolResult(True, text, data, untrusted=True)


async def _document(ctx: "ToolContext", url: str) -> ToolResult:
    doc = await ctx.browser.fetch_document(url)
    await ctx.emit("document", {"url": doc["url"], "content_type": doc["content_type"], "status": doc["status"],
                                "chars": len(doc.get("text", "")), "step": ctx.step})
    if doc["status"] >= 400:
        kind = "transient" if doc["status"] >= 500 else ("auth" if doc["status"] in (401, 403) else "unknown")
        return ToolResult(False, f"Fetching {doc['url']} failed with HTTP {doc['status']}.", doc, error_kind=kind)
    final = doc.get("final_url", doc["url"])
    note = ""
    if "/login" in final and "pdf" not in doc["content_type"]:
        return ToolResult(False, f"Document request was redirected to a sign-in page ({final}). The session is "
                                 f"missing or expired.", doc, error_kind="auth")
    text = doc["text"] or "(document contains no extractable text)"
    return ToolResult(True, f"Document {doc['url']} ({doc['content_type']}){note}:\n{text}",
                      {k: v for k, v in doc.items() if k != "text"} | {"preview": text[:400]}, untrusted=True)


@tool("browser_goto", "Open a URL in the browser (company apps or the public web) and return the page.",
      {"url": {"type": "string", "description": "Absolute URL"}}, ["url"], browser=True, verifier=True)
async def browser_goto(ctx: "ToolContext", url: str) -> ToolResult:
    if DOC_HREF.search(url):
        return await _document(ctx, url)
    try:
        await ctx.browser.goto(url)
    except Exception as e:  # PDFs and other downloads cannot be rendered by headless Chromium
        if "Download is starting" in str(e):
            return await _document(ctx, url)
        raise
    return await _observation(ctx, f"Navigated to {url}.", "goto")


@tool("browser_observe", "Re-read the current page (fresh element refs). Use after errors or when unsure of state.",
      browser=True, verifier=True)
async def browser_observe(ctx: "ToolContext") -> ToolResult:
    return await _observation(ctx, "Current page:", "observe")


@tool("browser_click", "Click an element by ref (links, buttons, submit). Document links are opened and read automatically.",
      {"ref": REF}, ["ref"], idempotent=False, browser=True, verifier=True)
async def browser_click(ctx: "ToolContext", ref: int) -> ToolResult:
    info = await ctx.browser.element_info(ref)
    if info is None:
        return ToolResult(False, f"Element [{ref}] not found on the current page.", error_kind="element_not_found")
    if ctx.verifier_mode and info["tag"] != "A":
        return ToolResult(False, "Verifier is read-only: only links may be clicked.", error_kind="policy")
    if info["tag"] == "A" and info.get("href") and DOC_HREF.search(info["href"]):
        return await _document(ctx, info["href"])
    await ctx.capture("target", highlight_ref=ref, extra={"target": info.get("text", "")})
    await ctx.browser.click(ref)
    return await _observation(ctx, f"Clicked [{ref}] {info['tag'].lower()} \"{info.get('text', '')}\".", "click")


@tool("browser_type", "Fill a text input / textarea / date input by ref (replaces existing value). "
      "Use {{secret:name}} for credentials - never type real secrets. Dates for date inputs: YYYY-MM-DD.",
      {"ref": REF, "text": {"type": "string"},
       "submit": {"type": "boolean", "description": "Press Enter after typing (submits the form)."}},
      ["ref", "text"], idempotent=False, browser=True)
async def browser_type(ctx: "ToolContext", ref: int, text: str, submit: bool = False) -> ToolResult:
    if await ctx.browser.element_info(ref) is None:
        return ToolResult(False, f"Element [{ref}] not found on the current page.", error_kind="element_not_found")
    real = ctx.vault.resolve(text)
    await ctx.browser.type(ref, real, submit)
    shown = text if ctx.vault.has_placeholder(text) else text[:80]
    if submit:
        return await _observation(ctx, f"Typed \"{shown}\" into [{ref}] and pressed Enter.", "submit")
    await ctx.capture("type", highlight_ref=ref)
    return ToolResult(True, f"Typed \"{shown}\" into [{ref}]. (Refs unchanged; observe if you need to confirm.)",
                      {"ref": ref})


@tool("browser_select", "Choose an option in a <select> dropdown by its visible label.",
      {"ref": REF, "option": {"type": "string", "description": "Visible option text"}}, ["ref", "option"],
      idempotent=False, browser=True)
async def browser_select(ctx: "ToolContext", ref: int, option: str) -> ToolResult:
    if await ctx.browser.element_info(ref) is None:
        return ToolResult(False, f"Element [{ref}] not found on the current page.", error_kind="element_not_found")
    chosen = await ctx.browser.select(ref, option)
    await ctx.capture("select", highlight_ref=ref)
    return ToolResult(True, f"Selected \"{option}\" (value: {chosen}) in [{ref}].", {"ref": ref})


@tool("browser_back", "Go back to the previous page.", browser=True, verifier=True)
async def browser_back(ctx: "ToolContext") -> ToolResult:
    await ctx.browser.back()
    return await _observation(ctx, "Went back.", "back")


@tool("browser_scroll", "Scroll the page up or down.",
      {"direction": {"type": "string", "enum": ["up", "down"]}}, ["direction"], browser=True, verifier=True)
async def browser_scroll(ctx: "ToolContext", direction: str) -> ToolResult:
    await ctx.browser.scroll(direction)
    return await _observation(ctx, f"Scrolled {direction}.", "scroll")


@tool("read_document", "Download a document (PDF, text) by URL using the browser's session and return its text.",
      {"url": {"type": "string"}}, ["url"], verifier=True)
async def read_document(ctx: "ToolContext", url: str) -> ToolResult:
    return await _document(ctx, url)
