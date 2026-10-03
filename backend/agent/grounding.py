"""Grounding check: values the agent is about to commit must come from something it actually observed.

Before a critical form submission (financial / irreversible), every amount, date and ID in the form must appear
in an observed page, document or API response, or in the user's own request. This catches transcription slips and
hallucinated numbers (e.g. typing 7142.18 when the invoice says 7,342.18) *before* they reach the system of record.
"""
from __future__ import annotations

import re

AMOUNT_RE = re.compile(r"(?<![\w.-])\$?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?(?![\d])|(?<![\w.-])\$?\d+\.\d{1,2}(?![\d])")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
ID_RE = re.compile(r"\b[A-Z]{2,}-\d{2,}\b")


def _amounts(text: str) -> set[str]:
    out = set()
    for m in AMOUNT_RE.findall(text or ""):
        try:
            out.add(f"{float(m.replace('$', '').replace(',', '')):.2f}")
        except ValueError:
            pass
    return out


def values(text: str) -> set[str]:
    """Checkable values in a piece of text, normalised (amounts to 2 decimals, IDs upper-case)."""
    text = text or ""
    return _amounts(text) | set(DATE_RE.findall(text)) | {i.upper() for i in ID_RE.findall(text.upper())}


class GroundingIndex:
    def __init__(self, goal: str) -> None:
        self._seen: set[str] = values(goal)

    def observe(self, text: str) -> None:
        self._seen |= values(text)

    def ungrounded(self, field_values: list[str]) -> list[str]:
        missing = []
        for v in field_values:
            for norm in sorted(values(v)):
                if norm not in self._seen:
                    missing.append(norm)
        return missing
