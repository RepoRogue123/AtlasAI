"""Working memory: facts discovered during a run, each with provenance (where it came from, at which step).

Facts are rendered into every prompt, so the model never has to re-derive a value it already found, and they
are surfaced in the final report as evidence ("amount 4,820.50 - from Acme_INV-2041.pdf, step 6").
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Fact:
    key: str
    value: str
    source: str
    step: int
    screenshot: str | None = None


class WorkingMemory:
    def __init__(self) -> None:
        self.facts: dict[str, Fact] = {}

    def remember(self, key: str, value: str, source: str, step: int, screenshot: str | None = None) -> Fact:
        fact = Fact(key.strip(), str(value).strip(), source.strip(), step, screenshot)
        self.facts[fact.key] = fact
        return fact

    def digest(self) -> str:
        if not self.facts:
            return "(nothing remembered yet)"
        return "\n".join(f"- {f.key}: {f.value}   [source: {f.source}, step {f.step}]" for f in self.facts.values())

    def as_list(self) -> list[dict]:
        return [asdict(f) for f in self.facts.values()]
