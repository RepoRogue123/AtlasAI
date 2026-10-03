"""Playwright browser session: real Chromium, one isolated context per run."""
from __future__ import annotations

import asyncio
import io
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from pypdf import PdfReader

from config import HEADLESS

SNAPSHOT_JS = (Path(__file__).parent / "snapshot.js").read_text(encoding="utf-8")
DOC_HREF = re.compile(r"(\.pdf($|[?#]))|(/pdf($|[?#]))|(/attachments/)", re.I)
MAX_SNAPSHOT_CHARS = 9000
ACTION_TIMEOUT_MS = 6000


class BrowserManager:
    """Process-wide Playwright + Chromium, lazily started and shared by all runs."""

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def browser(self) -> Browser:
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                self._pw = self._pw or await async_playwright().start()
                self._browser = await self._pw.chromium.launch(headless=HEADLESS)
            return self._browser

    async def new_session(self, shots_dir: Path) -> "BrowserSession":
        context = await (await self.browser()).new_context(viewport={"width": 1280, "height": 800},
                                                             accept_downloads=False)
        session = BrowserSession(context, shots_dir)
        await session.open_page()
        return session

    async def shutdown(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser, self._pw = None, None


MANAGER = BrowserManager()


def pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages).strip()


class BrowserSession:
    def __init__(self, context: BrowserContext, shots_dir: Path) -> None:
        self.context = context
        self.page: Page | None = None
        self.shots_dir = shots_dir
        shots_dir.mkdir(parents=True, exist_ok=True)
        self.last_doc_status: int | None = None
        self.shot_counter = 0
        self.shot_prefix = ""
        self.last_snapshot: dict[str, Any] | None = None

    async def open_page(self) -> Page:
        self.page = await self.context.new_page()
        self.page.set_default_timeout(ACTION_TIMEOUT_MS)

        def on_response(resp):
            try:
                if resp.request.is_navigation_request() and resp.frame == self.page.main_frame:
                    self.last_doc_status = resp.status
            except Exception:
                pass
        self.page.on("response", on_response)
        return self.page

    async def close(self) -> None:
        await self.context.close()

    # ------------------------------------------------------------------ observation
    async def observe(self) -> dict[str, Any]:
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        if self.page.url == "about:blank":
            snap = {"url": "about:blank", "title": "", "text": "(blank page - use browser_goto)", "refs": 0, "modal": None}
        else:
            snap = await self.page.evaluate(SNAPSHOT_JS)
        if len(snap["text"]) > MAX_SNAPSHOT_CHARS:
            snap["text"] = snap["text"][:MAX_SNAPSHOT_CHARS] + "\n... (page truncated - scroll or navigate more specifically)"
        snap["status"] = self.last_doc_status
        self.last_snapshot = snap
        return snap

    @staticmethod
    def render(snap: dict[str, Any]) -> str:
        head = f"URL: {snap['url']}\nTitle: {snap['title']}"
        if snap.get("status") and snap["status"] >= 400:
            head += f"\nHTTP status of last page load: {snap['status']}"
        if snap.get("modal"):
            head += f"\n!! A modal dialog is open and blocks the page: \"{snap['modal']}\""
        return f"{head}\n--- page content ({snap['refs']} interactive elements) ---\n{snap['text']}"

    async def screenshot(self, tag: str) -> str:
        self.shot_counter += 1
        name = f"{self.shot_prefix}{self.shot_counter:03d}-{tag}.jpg"
        try:
            await self.page.screenshot(path=str(self.shots_dir / name), type="jpeg", quality=62)
        except Exception:
            return ""
        return name

    # ------------------------------------------------------------------ elements
    def _locator(self, ref: int):
        return self.page.locator(f'[data-atlas-ref="{int(ref)}"]')

    async def element_info(self, ref: int) -> dict[str, Any] | None:
        loc = self._locator(ref)
        if await loc.count() == 0:
            return None
        return await loc.first.evaluate("""el => {
            const form = el.closest('form');
            return {
              tag: el.tagName, type: (el.type || '').toLowerCase(),
              text: (el.innerText || el.value || el.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim().slice(0, 120),
              href: el.tagName === 'A' ? el.href : null,
              form_method: form ? (form.getAttribute('method') || 'get').toLowerCase() : null,
              form_action: form ? form.action : null,
              form_has_password: form ? !!form.querySelector('input[type=password]') : false,
              submit_like: el.tagName === 'BUTTON' ? (el.type || 'submit') === 'submit' : ['submit'].includes((el.type||'').toLowerCase()),
              fields: form ? [...form.querySelectorAll('input, select, textarea')]
                .filter(f => !['hidden', 'submit', 'button', 'password'].includes((f.type || '').toLowerCase()))
                .map(f => {
                  const l = f.id ? document.querySelector(`label[for="${CSS.escape(f.id)}"]`) : null;
                  return { label: ((l && l.innerText) || f.name || '').trim(),
                           value: f.tagName === 'SELECT' ? (f.selectedOptions[0] ? f.selectedOptions[0].text : '') : f.value };
                }) : [],
            };
        }""")

    async def highlight_shot(self, ref: int, tag: str) -> str:
        loc = self._locator(ref).first
        try:
            await loc.scroll_into_view_if_needed(timeout=2000)
            await loc.evaluate("el => { el.dataset.atlasOutline = el.style.outline; "
                               "el.style.outline = '3px solid #f43f5e'; el.style.outlineOffset = '2px'; }")
            name = await self.screenshot(tag)
            await loc.evaluate("el => { el.style.outline = el.dataset.atlasOutline || ''; el.style.outlineOffset = ''; }")
            return name
        except Exception:
            return ""

    async def _settle(self) -> None:
        try:
            await self.page.wait_for_load_state("load", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(0.25)

    # ------------------------------------------------------------------ actions
    async def goto(self, url: str) -> None:
        if not re.match(r"^https?://", url):
            url = "https://" + url
        self.last_doc_status = None
        await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await self._settle()

    async def click(self, ref: int) -> None:
        self.last_doc_status = None
        await self._locator(ref).first.click(timeout=ACTION_TIMEOUT_MS)
        await self._settle()

    async def type(self, ref: int, text: str, submit: bool) -> None:
        loc = self._locator(ref).first
        self.last_doc_status = None
        await loc.fill(text, timeout=ACTION_TIMEOUT_MS)
        if submit:
            await loc.press("Enter")
            await self._settle()

    async def select(self, ref: int, option: str) -> str:
        loc = self._locator(ref).first
        try:
            chosen = await loc.select_option(label=option, timeout=ACTION_TIMEOUT_MS)
        except Exception:
            chosen = await loc.select_option(value=option, timeout=ACTION_TIMEOUT_MS)
        return ", ".join(chosen)

    async def back(self) -> None:
        self.last_doc_status = None
        await self.page.go_back(wait_until="domcontentloaded")
        await self._settle()

    async def scroll(self, direction: str) -> None:
        await self.page.mouse.wheel(0, 700 if direction == "down" else -700)
        await asyncio.sleep(0.2)

    async def fetch_document(self, url: str) -> dict[str, Any]:
        """Download a document with the session's cookies and extract its text (PDF or text/html)."""
        url = urljoin(self.page.url if self.page.url.startswith("http") else "", url)
        resp = await self.context.request.get(url, timeout=20000)
        ctype = resp.headers.get("content-type", "")
        body = await resp.body()
        if resp.status >= 400:
            return {"url": url, "status": resp.status, "content_type": ctype, "text": body[:500].decode("utf-8", "ignore")}
        if "pdf" in ctype or body[:4] == b"%PDF":
            return {"url": url, "status": resp.status, "content_type": "application/pdf",
                    "text": pdf_text(body), "bytes": len(body), "final_url": resp.url}
        text = body.decode("utf-8", "ignore")
        if "html" in ctype:
            text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
        return {"url": url, "status": resp.status, "content_type": ctype, "text": text[:8000], "final_url": resp.url}
