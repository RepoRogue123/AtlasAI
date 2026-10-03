"""Tool registry. A tool = JSON schema + async handler + static risk metadata.

Every tool automatically gets a required `rationale` argument: the model must say *why* it is taking each
action. That rationale is shown in the live UI, in approval requests and in replays, which makes agent
decisions explainable after the fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

if TYPE_CHECKING:
    from agent.context import ToolContext

Risk = Literal["read", "write", "critical"]


@dataclass
class ToolResult:
    ok: bool
    output: str                                   # text the LLM sees
    data: dict[str, Any] = field(default_factory=dict)   # structured payload for UI / report
    error_kind: str | None = None                 # recovery taxonomy key when ok=False
    untrusted: bool = False                       # output contains third-party content (scan for injection)

    def for_llm(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok, "result": self.output}
        if self.error_kind:
            payload["error_kind"] = self.error_kind
        return payload


Handler = Callable[..., Awaitable[ToolResult]]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    required: list[str]
    handler: Handler
    risk: Risk = "read"
    idempotent: bool = True       # safe to auto-retry on transient failure
    browser: bool = False         # produces a new page state (screenshot afterwards)
    verifier: bool = False        # available to the read-only verifier agent

    def declaration(self) -> dict[str, Any]:
        props = dict(self.parameters)
        props["rationale"] = {"type": "string",
                              "description": "One short sentence: why this action, and what you expect to observe."}
        return {
            "name": self.name,
            "description": self.description,
            "parameters_json_schema": {
                "type": "object",
                "properties": props,
                "required": [*self.required, "rationale"],
            },
        }


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, description: str, parameters: dict[str, Any] | None = None, required: list[str] | None = None,
         *, risk: Risk = "read", idempotent: bool = True, browser: bool = False, verifier: bool = False):
    def wrap(fn: Handler) -> Handler:
        REGISTRY[name] = ToolSpec(name, description, parameters or {}, required or [], fn,
                                  risk, idempotent, browser, verifier)
        return fn
    return wrap


def load_all() -> dict[str, ToolSpec]:
    # Importing registers the tools via the decorator.
    from tools import browser_tools, core, files, http, vision  # noqa: F401
    return REGISTRY


def declarations(names: list[str] | None = None) -> list[dict[str, Any]]:
    specs = REGISTRY.values() if names is None else [REGISTRY[n] for n in names]
    return [s.declaration() for s in specs]
