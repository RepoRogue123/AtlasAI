"""Fallback LLM providers (Groq, OpenRouter) behind the same interface as the Gemini adapter.

Both expose the OpenAI-compatible `/chat/completions` API, so one class serves both. The kernel keeps its history
as Gemini `types.Content` objects; this module translates that history into OpenAI messages and translates the reply
back into a Gemini-shaped `Content`, so the kernel, verifier and planner run unchanged on any provider.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from google.genai import types

import config


class ProviderError(RuntimeError):
    pass


# Preferred tool-capable models, most capable first. Used when no model is configured explicitly.
GROQ_PREFERENCE = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "moonshotai/kimi-k2-instruct",
                   "qwen/qwen3-32b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
OPENROUTER_PREFERENCE = ["deepseek", "qwen3", "gpt-oss", "llama-3.3-70b", "kimi", "glm", "mistral", "gemma"]


@dataclass
class OpenAICompatProvider:
    name: str
    base_url: str
    api_key: str
    model: str = "auto"
    vision_model: str = "auto"
    headers: dict[str, str] = field(default_factory=dict)
    _resolved: str | None = None
    _resolved_vision: str | None = None
    _disabled_until: float = 0.0
    last_error: str = ""

    # ------------------------------------------------------------------ model selection
    async def _list_models(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{self.base_url}/models", headers=self._auth())
            r.raise_for_status()
            return r.json().get("data", [])

    async def resolve(self) -> str:
        if self._resolved:
            return self._resolved
        if self.model and self.model != "auto":
            self._resolved = self.model
            return self._resolved
        models = await self._list_models()
        if self.name == "openrouter":
            # Free models (price 0) that accept tool calls; prefer strong families, then longest context.
            # Unnamed "stealth/" preview models are excluded: provenance and data handling are unknown.
            free = [m for m in models
                    if not m["id"].startswith("stealth/")
                    and str(m.get("pricing", {}).get("prompt")) in ("0", "0.0")
                    and str(m.get("pricing", {}).get("completion")) in ("0", "0.0")
                    and "tools" in (m.get("supported_parameters") or [])]
            def rank(m):
                pref = next((i for i, p in enumerate(OPENROUTER_PREFERENCE) if p in m["id"]), len(OPENROUTER_PREFERENCE))
                return (pref, -(m.get("context_length") or 0))
            free.sort(key=rank)
            if not free:
                raise ProviderError("OpenRouter lists no free tool-capable model")
            self._resolved = free[0]["id"]
        else:
            ids = {m["id"] for m in models}
            self._resolved = next((m for m in GROQ_PREFERENCE if m in ids), None) or next(iter(sorted(ids)), None)
            if not self._resolved:
                raise ProviderError("Groq lists no models")
        return self._resolved

    async def resolve_vision(self) -> str:
        if self._resolved_vision:
            return self._resolved_vision
        if self.vision_model and self.vision_model != "auto":
            self._resolved_vision = self.vision_model
            return self._resolved_vision
        models = await self._list_models()
        if self.name == "openrouter":
            cands = [m["id"] for m in models
                     if not m["id"].startswith("stealth/")
                     and str(m.get("pricing", {}).get("prompt")) in ("0", "0.0")
                     and "image" in (m.get("architecture", {}).get("input_modalities") or [])]
        else:
            cands = [m["id"] for m in models if re.search(r"llama-4|vision|scout|maverick", m["id"])]
        if not cands:
            raise ProviderError(f"{self.name} lists no vision model")
        self._resolved_vision = cands[0]
        return self._resolved_vision

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", **self.headers}

    @property
    def available(self) -> bool:
        return bool(self.api_key) and time.time() >= self._disabled_until

    # ------------------------------------------------------------------ transport
    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /chat/completions with bounded retries. Raises ProviderError when this provider should be skipped."""
        last = ""
        for attempt in range(1, 6):
            try:
                async with httpx.AsyncClient(timeout=120) as c:
                    r = await c.post(f"{self.base_url}/chat/completions", headers=self._auth(), json=body)
            except httpx.HTTPError as e:
                last = f"network: {e}"
                await asyncio.sleep(2 * attempt)
                continue
            if r.status_code == 200:
                data = r.json()
                if "error" in data:            # OpenRouter reports upstream failures inside a 200
                    last = str(data["error"])[:300]
                    await asyncio.sleep(2 * attempt)
                    continue
                return data
            last = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code in (401, 403):
                self._disabled_until = time.time() + 24 * 3600      # bad key: stop trying this process
                self.last_error = f"key rejected ({last})"
                break
            if r.status_code == 400:
                err = ProviderError(f"{self.name} rejected the request: {last}")
                try:
                    err.body = r.json()
                except ValueError:
                    err.body = {}
                raise err
            if r.status_code == 429:
                # Free tiers rate-limit per minute; waiting up to 90 s keeps a run alive on the last provider.
                wait = float(r.headers.get("retry-after", "0") or 0) or 5.0 * attempt
                if wait > 90 or attempt == 5:   # per-minute token limits (Groq free: 8k TPM) reset within ~60-90 s
                    self._disabled_until = time.time() + max(wait, 60)
                    self.last_error = f"rate-limited ({last})"
                    break
                await asyncio.sleep(wait)
                continue
            await asyncio.sleep(2 * attempt)                          # 5xx and anything else
        self.last_error = self.last_error or last
        raise ProviderError(f"{self.name} unavailable ({last})")

    # ------------------------------------------------------------------ high level
    async def act(self, system: str, contents: list, tools: list[dict]) -> tuple[types.Content, str, list[str], dict]:
        body = {
            "model": await self.resolve(),
            "messages": to_messages(system, contents),
            "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                         "parameters": t["parameters_json_schema"]}} for t in tools],
            "tool_choice": "required",
            "parallel_tool_calls": False,
        }
        thoughts: list[str] = []
        try:
            data = await self.chat(body)
        except ProviderError as e:
            if "rejected the request" not in str(e):
                raise
            # Groq returns 400 "tool_use_failed" when the model's tool call is malformed, with the raw output in
            # `failed_generation`. Recover the call from that text before retrying with a looser request.
            error = (getattr(e, "body", None) or {}).get("error") or {}
            call = salvage_tool_call(error.get("failed_generation") or "", tools) if isinstance(error, dict) else None
            if call:
                note = f"[runtime] recovered a malformed tool call from {self.name} (tool_use_failed)"
                return content_for_calls([call], ""), "", [note], {}
            body.pop("parallel_tool_calls")            # some upstream models reject these options
            body["tool_choice"] = "auto"
            data = await self.chat(body)
        msg = data["choices"][0]["message"]
        if isinstance(msg.get("reasoning"), str) and msg["reasoning"].strip():
            thoughts.append(msg["reasoning"])
        text = msg.get("content") or ""
        calls = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append((tc["function"]["name"], args, tc.get("id")))
        if not calls and (call := salvage_tool_call(text, tools)):
            # The model wrote the call as JSON text instead of a tool call (gpt-oss on Groq, 2026-10-03).
            calls, text = [call], ""
            thoughts.append(f"[runtime] recovered a tool call that {self.name} returned as text")
        return content_for_calls(calls, text), text, thoughts, data.get("usage") or {}

    async def json(self, system: str, prompt: str, schema: dict[str, Any]) -> tuple[dict, dict]:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": f"{prompt}\n\nRespond ONLY with a JSON object that matches this "
                                                f"JSON schema:\n{json.dumps(schema)}"}]
        body = {"model": await self.resolve(), "messages": messages, "response_format": {"type": "json_object"}}
        try:
            data = await self.chat(body)
        except ProviderError as e:
            if "rejected the request" not in str(e):
                raise
            body.pop("response_format")
            data = await self.chat(body)
        text = data["choices"][0]["message"].get("content") or "{}"
        m = re.search(r"\{.*\}", text, re.S)
        return (json.loads(m.group()) if m else {}), data.get("usage") or {}

    async def vision(self, image: bytes, question: str, mime_type: str) -> tuple[str, dict]:
        url = f"data:{mime_type};base64,{base64.b64encode(image).decode()}"
        body = {"model": await self.resolve_vision(), "messages": [{"role": "user", "content": [
            {"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": url}}]}]}
        data = await self.chat(body)
        return (data["choices"][0]["message"].get("content") or "").strip(), data.get("usage") or {}


def content_for_calls(calls: list[tuple[str, dict, str | None]], text: str) -> types.Content:
    parts: list[types.Part] = [types.Part(text=text)] if text else []
    for name, args, cid in calls:
        parts.append(types.Part(function_call=types.FunctionCall(
            name=name, args=args, id=cid or f"call_{uuid.uuid4().hex[:8]}")))
    return types.Content(role="model", parts=parts or [types.Part(text="(empty reply)")])


def _json_objects(text: str) -> list[dict]:
    """Every top-level JSON object embedded in `text` (models wrap them in prose or code fences)."""
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(text or ""):
        if in_str:                       # braces inside JSON strings must not count
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start:i + 1])
                    if isinstance(obj, dict):
                        out.append(obj)
                except json.JSONDecodeError:
                    pass
    return out


def salvage_tool_call(text: str, tools: list[dict]) -> tuple[str, dict, None] | None:
    """Recover a tool call that a model emitted as text instead of a structured tool call.

    Accepts {"name": tool, "arguments"|"parameters": {...}} or a bare argument object whose keys include every
    required parameter of exactly one tool and nothing outside its schema. Returns None when ambiguous: a wrong guess
    would execute an action the model did not choose.
    """
    if not text or not tools:
        return None
    by_name = {t["name"]: t for t in tools}
    for obj in _json_objects(text):
        name = obj.get("name") or obj.get("tool") or obj.get("function")
        args = obj.get("arguments", obj.get("parameters", obj.get("args")))
        if isinstance(name, str) and name in by_name:
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = None
            if isinstance(args, dict):
                return name, args, None
        keys = set(obj)
        matches = []
        for t in tools:
            schema = t.get("parameters_json_schema", {})
            required = set(schema.get("required", [])) - {"rationale"}
            props = set(schema.get("properties", {}))
            if required and required <= keys <= props:
                matches.append((len(keys & props), t["name"]))
        matches.sort(reverse=True)
        if len(matches) == 1 or (len(matches) > 1 and matches[0][0] > matches[1][0]):
            return matches[0][1], obj, None
    return None


def to_messages(system: str, contents: list) -> list[dict[str, Any]]:
    """Gemini `Content` history -> OpenAI chat messages (system, user, assistant tool_calls, tool results)."""
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    pending_ids: list[str] = []
    for ci, c in enumerate(contents):
        if isinstance(c, str):
            msgs.append({"role": "user", "content": c})
            continue
        texts, calls, responses = [], [], []
        for p in c.parts or []:
            if p.function_call:
                calls.append(p.function_call)
            elif p.function_response:
                responses.append(p.function_response)
            elif p.text and not p.thought:       # Gemini thought summaries are not part of the conversation
                texts.append(p.text)
        if c.role == "model":
            m: dict[str, Any] = {"role": "assistant", "content": "\n".join(texts) or None}
            if calls:
                pending_ids = [fc.id or f"call_{ci}_{i}" for i, fc in enumerate(calls)]
                m["tool_calls"] = [{"id": tid, "type": "function",
                                    "function": {"name": fc.name, "arguments": json.dumps(fc.args or {})}}
                                   for tid, fc in zip(pending_ids, calls)]
            msgs.append(m)
        else:
            for i, fr in enumerate(responses):
                tid = fr.id or (pending_ids[i] if i < len(pending_ids) else f"call_{ci}_{i}")
                msgs.append({"role": "tool", "tool_call_id": tid, "name": fr.name,
                             "content": json.dumps(fr.response, default=str)})
            if texts:
                msgs.append({"role": "user", "content": "\n".join(texts)})
    return msgs


def configured() -> list[OpenAICompatProvider]:
    """Fallback providers in priority order: Groq, then OpenRouter (only those with a key)."""
    out = []
    if config.GROQ_API_KEY:
        out.append(OpenAICompatProvider("groq", "https://api.groq.com/openai/v1", config.GROQ_API_KEY,
                                        config.GROQ_MODEL, config.GROQ_VISION_MODEL))
    if config.OPENROUTER_API_KEY:
        out.append(OpenAICompatProvider("openrouter", "https://openrouter.ai/api/v1", config.OPENROUTER_API_KEY,
                                        config.OPENROUTER_MODEL, config.OPENROUTER_VISION_MODEL,
                                        headers={"X-Title": "Atlas AI task worker"}))
    return out
