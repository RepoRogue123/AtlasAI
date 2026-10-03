"""Goal understanding: turn a natural-language request into an initial plan + explicit success criteria.

The success criteria matter most: they are what the independent verifier checks at the end, so "done" is
defined up front by the user's intent rather than by whatever the agent happened to do.
"""
from __future__ import annotations

import config
from agent.llm import LLM

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "understanding": {"type": "string", "description": "The user's real end goal in one or two sentences."},
        "steps": {"type": "array", "items": {"type": "string"}, "description": "3-8 high-level steps"},
        "success_criteria": {"type": "array", "items": {"type": "string"},
                             "description": "Observable, checkable conditions that prove the goal was achieved"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "ambiguities": {"type": "array", "items": {"type": "string"},
                        "description": "Things that may need the user's clarification (empty if none)"},
    },
    "required": ["understanding", "steps", "success_criteria", "assumptions", "ambiguities"],
}

PLANNER_SYSTEM = """You are the planning module of Atlas, an autonomous AI worker.
Given a user's request and a description of the environment, produce a short high-level plan.
- Infer the user's END GOAL; do not require every step to be specified.
- Steps are high level (the executor will discover the details by exploring the apps).
- Success criteria must be concrete and verifiable by looking at the systems afterwards
  (e.g. "A bill for Acme Supplies with invoice INV-123, amount X and due date Y exists in the ERP, exactly once").
  Use placeholders when values are not yet known (e.g. "amount equals the invoice total").
- If the task includes informing the user, the final summary counts; do not invent a messaging step.
- List genuine ambiguities only (e.g. several candidates may match).
"""


async def make_plan(llm: LLM, goal: str, environment: str, skill_hint: str = "") -> dict:
    prompt = f"ENVIRONMENT:\n{environment}\n\n"
    if skill_hint:
        prompt += f"RELEVANT EXPERIENCE FROM PAST RUNS:\n{skill_hint}\n\n"
    prompt += f"USER REQUEST:\n{goal}"
    plan = await llm.json(PLANNER_SYSTEM, prompt, PLAN_SCHEMA, model=config.GEMINI_REASONING_MODEL)
    for key in ("steps", "success_criteria", "assumptions", "ambiguities"):
        plan.setdefault(key, [])
    plan.setdefault("understanding", goal)
    return plan
