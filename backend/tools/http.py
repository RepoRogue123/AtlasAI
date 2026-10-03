"""HTTP API + web search tools (read-only, host allow-list)."""
from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from config import HTTP_ALLOWLIST
from tools.registry import ToolResult, tool

if TYPE_CHECKING:
    from agent.context import ToolContext

# Wikimedia's user-agent policy rejects (403) clients without contact details in the UA string.
UA = {"User-Agent": "AtlasAgent/1.0 (research prototype; atlas-agent@example.com)"}


@tool("http_get", "HTTP GET a JSON/text API on an allow-listed host (company APIs, Wikipedia API). Read-only.",
      {"url": {"type": "string"}}, ["url"], verifier=True)
async def http_get(ctx: "ToolContext", url: str) -> ToolResult:
    host = urlparse(url).netloc
    if host not in HTTP_ALLOWLIST:
        return ToolResult(False, f"Host '{host}' is not allow-listed. Allowed: {', '.join(HTTP_ALLOWLIST)}",
                          error_kind="policy")
    async with httpx.AsyncClient(timeout=15, headers=UA, follow_redirects=True) as client:
        r = await client.get(url)
    if r.status_code >= 400:
        kind = "transient" if r.status_code >= 500 else "unknown"
        return ToolResult(False, f"HTTP {r.status_code}: {r.text[:300]}", error_kind=kind)
    await ctx.emit("http", {"url": url, "status": r.status_code, "step": ctx.step})
    return ToolResult(True, r.text[:8000], {"url": url, "status": r.status_code}, untrusted=True)


def _ddg_results(page: str, limit: int) -> list[dict]:
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
                         r'(?:class="result__snippet"[^>]*>(.*?)</a>)?', page, re.S):
        href = html.unescape(m.group(1))
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        strip = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()
        out.append({"title": strip(m.group(2)), "url": href, "snippet": strip(m.group(3))})
        if len(out) >= limit:
            break
    return out


@tool("web_search", "Search the public web. Returns titles, URLs and snippets; open a result with browser_goto.",
      {"query": {"type": "string"}}, ["query"], verifier=True)
async def web_search(ctx: "ToolContext", query: str) -> ToolResult:
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=15, headers=UA, follow_redirects=True) as c:
        try:   # DuckDuckGo answers automated clients with a 202 challenge page; then fall through to Wikipedia
            r = await c.get(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
                            headers={"User-Agent": "Mozilla/5.0"})
            results = _ddg_results(r.text, 6) if r.status_code == 200 else []
        except httpx.HTTPError:
            pass
        if not results:  # fallback: Wikipedia search API
            try:
                r = await c.get("https://en.wikipedia.org/w/api.php", params={
                    "action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 5})
                for item in r.json().get("query", {}).get("search", []):
                    title = item["title"]
                    results.append({"title": title, "url": f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
                                    "snippet": html.unescape(re.sub(r"<[^>]+>", "", item.get("snippet", "")))})
            except (httpx.HTTPError, ValueError):
                pass
    await ctx.emit("search", {"query": query, "results": results, "step": ctx.step})
    if not results:
        return ToolResult(False, "Search returned no results (network may be unavailable).", error_kind="transient")
    text = "\n".join(f"{i + 1}. {r['title']} - {r['url']}\n   {r['snippet']}" for i, r in enumerate(results))
    return ToolResult(True, text, {"results": results}, untrusted=True)
