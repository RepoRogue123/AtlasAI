"""Fallback providers: history translation and the Gemini -> Groq/OpenRouter hand-over (no network)."""
from google.genai import types

from agent import llm as llm_mod
from agent import providers
from agent.llm import LLM, GeminiUnavailable


def test_gemini_history_translates_to_openai_messages():
    contents = [
        types.Content(role="user", parts=[types.Part(text="TASK: enter the invoice")]),
        types.Content(role="model", parts=[
            types.Part(text="internal reasoning", thought=True),           # thought summaries are dropped
            types.Part(function_call=types.FunctionCall(name="browser_goto", args={"url": "http://x/mail"}))]),
        types.Content(role="user", parts=[types.Part.from_function_response(name="browser_goto",
                                                                            response={"ok": True, "result": "Inbox"})]),
    ]
    msgs = providers.to_messages("SYSTEM", contents)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool"]
    call = msgs[2]["tool_calls"][0]
    assert call["function"]["name"] == "browser_goto" and '"http://x/mail"' in call["function"]["arguments"]
    assert msgs[2]["content"] is None                                    # the thought did not leak into content
    assert msgs[3]["tool_call_id"] == call["id"] and '"Inbox"' in msgs[3]["content"]


class FakeProvider:
    name = "groq"
    available = True

    def __init__(self):
        self.calls = 0

    async def resolve(self):
        return "fake-model"

    async def act(self, system, contents, tools):
        self.calls += 1
        content = types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(
            name="finish", args={"outcome": "success", "summary": "ok"}, id="call_1"))])
        return content, "", [], {"prompt_tokens": 10, "completion_tokens": 5}


async def test_act_falls_back_and_stays_on_fallback(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(providers, "configured", lambda: [fake])
    llm = LLM()
    gemini_calls = []

    async def gemini_down(*a, **k):
        gemini_calls.append(1)
        raise GeminiUnavailable("all Gemini models overloaded")
    monkeypatch.setattr(llm, "_act_gemini", gemini_down)

    reply = await llm.act("sys", [types.Content(role="user", parts=[types.Part(text="hi")])], [])
    assert reply.calls[0].name == "finish" and reply.calls[0].id == "call_1"
    assert llm.sticky is fake and llm.usage.fallback_calls == 1 and llm.usage.fallback_tokens == 15
    await llm.act("sys", [], [])                       # second turn: Gemini is not retried mid-run
    assert len(gemini_calls) == 1 and fake.calls == 2
    assert await llm.label() == "groq:fake-model"


async def test_no_fallback_configured_surfaces_gemini_error(monkeypatch):
    monkeypatch.setattr(providers, "configured", lambda: [])
    llm = LLM()

    async def gemini_down(*a, **k):
        raise GeminiUnavailable("down")
    monkeypatch.setattr(llm, "_act_gemini", gemini_down)
    try:
        await llm.act("sys", [], [])
        raise AssertionError("expected GeminiUnavailable")
    except GeminiUnavailable:
        pass


def test_llm_requires_some_key(monkeypatch):
    monkeypatch.setattr(llm_mod.config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(providers, "configured", lambda: [])
    try:
        LLM()
        raise AssertionError("expected LLMError")
    except llm_mod.LLMError as e:
        assert "No LLM key" in str(e)


def _decls(*names):
    from tools.registry import REGISTRY, load_all
    load_all()
    return [REGISTRY[n].declaration() for n in names]


def test_salvage_real_groq_finish_written_as_text():
    """Regression: gpt-oss-120b on Groq wrote its finish call as JSON text for 7 turns (eval-invoice_email-a5e0ce)."""
    from pathlib import Path
    text = (Path(__file__).parent / "fixtures_groq_finish_as_text.txt").read_text(encoding="utf-8")
    tools = _decls("browser_goto", "browser_click", "remember", "update_plan", "finish")
    name, args, _ = providers.salvage_tool_call(text, tools)
    assert name == "finish" and args["outcome"] == "success" and args["results"][1]["value"] == "4820.50"


def test_salvage_named_call_and_refuses_ambiguity():
    tools = _decls("browser_goto", "read_document", "remember", "finish")
    wrapped = 'Sure:\n```json\n{"name": "browser_goto", "arguments": {"url": "http://x/{a}"}}\n```'
    assert providers.salvage_tool_call(wrapped, tools) == ("browser_goto", {"url": "http://x/{a}"}, None)
    # {"url": ...} fits both browser_goto and read_document equally well: refuse to guess.
    assert providers.salvage_tool_call('{"url": "http://x/doc.pdf"}', tools) is None
    assert providers.salvage_tool_call("I will now open the inbox.", tools) is None
