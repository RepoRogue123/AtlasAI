"""Skill library: turning successful runs into reusable capabilities.

After a *verified* success, the trajectory is distilled into a parameterised procedure (what worked, which pages,
which pitfalls were hit). Future tasks retrieve the best-matching skill and receive it as guidance, which cuts
exploration steps. Skills are hints, not scripts: the agent still observes and adapts, so a changed UI does not
break it.
"""
from __future__ import annotations

import re

from agent.llm import LLM
from agent.store import Store

STOP = set("the a an and or of to for in on at by with from into our my me it is be this that then once tell "
           "done please i we you find enter latest new".split())

SKILL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "snake_case capability name, e.g. enter_vendor_invoice_from_email"},
        "summary": {"type": "string"},
        "applies_when": {"type": "string", "description": "What kinds of requests this skill helps with"},
        "procedure": {"type": "array", "items": {"type": "string"},
                      "description": "Generalised steps with concrete URLs/page names, parameterised (e.g. <vendor>)"},
        "pitfalls": {"type": "array", "items": {"type": "string"}, "description": "Problems hit and how they were solved"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "summary", "applies_when", "procedure", "pitfalls", "keywords"],
}

DISTILL_SYSTEM = """You turn a successful AI-agent run into a reusable skill for future, similar requests.
Generalise: replace run-specific values (vendor names, amounts, ids) with <placeholders>, but keep concrete,
useful navigation knowledge (URLs, page/field names, formats). Include pitfalls actually encountered.
If an existing skill is provided, merge the new knowledge into it instead of creating a different one."""


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 2}


def find(store: Store, goal: str, threshold: float = 0.18) -> dict | None:
    goal_t = _tokens(goal)
    best, best_score = None, 0.0
    for s in store.skills():
        skill_t = _tokens(" ".join([s["name"].replace("_", " "), s["applies_when"], " ".join(s["keywords"])]))
        if not skill_t or not goal_t:
            continue
        score = len(goal_t & skill_t) / (len(goal_t) * len(skill_t)) ** 0.5   # cosine over token sets
        if score > best_score:
            best, best_score = s, score
    if best and best_score >= threshold:
        return {**best, "score": round(best_score, 3)}
    return None


def render(skill: dict) -> str:
    steps = "\n".join(f"  {i + 1}. {p}" for i, p in enumerate(skill["procedure"]))
    pitfalls = "\n".join(f"  - {p}" for p in skill["pitfalls"]) or "  - (none recorded)"
    return (f"Skill '{skill['name']}' (succeeded {skill['successes']}x): {skill['summary']}\n"
            f"Procedure that worked before:\n{steps}\nPitfalls:\n{pitfalls}\n"
            f"Use it as guidance; verify each step against what you actually observe.")


async def learn(llm: LLM, store: Store, run_id: str, goal: str, trajectory: str, existing: dict | None) -> dict:
    prompt = f"USER REQUEST:\n{goal}\n\nSUCCESSFUL TRAJECTORY (actions and outcomes):\n{trajectory}\n"
    if existing:
        prompt += f"\nEXISTING SKILL TO MERGE INTO:\n{render(existing)}\n"
    skill = await llm.json(DISTILL_SYSTEM, prompt, SKILL_SCHEMA)
    if existing:
        store.update_skill(existing["id"], skill)
        return {**skill, "id": existing["id"], "merged": True}
    skill_id = store.add_skill(skill, run_id)
    return {**skill, "id": skill_id, "merged": False}
