"""Failure taxonomy -> recovery strategy.

The kernel auto-retries transient failures of idempotent tools (with backoff). Everything else is returned to
the model with a classified error and a concrete hint, so its next decision is informed rather than a blind retry.
"""
from __future__ import annotations

import re

RULES: list[tuple[str, re.Pattern]] = [
    ("download", re.compile(r"Download is starting", re.I)),
    ("blocked_by_overlay", re.compile(r"intercepts pointer events|obscur|another element would receive the click", re.I)),
    ("element_not_found", re.compile(r"not found|no element|waiting for locator|strict mode violation|element is not attached", re.I)),
    ("validation", re.compile(r"malformed value|not a valid|invalid|422|cannot type|not an <input>", re.I)),
    ("auth", re.compile(r"\b(401|403)\b|unauthori[sz]ed|forbidden|session (has )?expired|please sign in", re.I)),
    ("transient", re.compile(r"\b50[0234]\b|timeout|timed out|net::ERR|ECONNRESET|ECONNREFUSED|temporarily unavailable|"
                             r"target closed|connection (reset|closed)", re.I)),
]

HINTS = {
    "transient": "Transient failure (server error / timeout). Retry the step; if it keeps failing, reload the page "
                 "or take an alternative route. For form submissions, first check whether the record was created "
                 "before re-submitting.",
    "blocked_by_overlay": "Another element (e.g. a modal or consent banner) covers the target. Observe the page, "
                          "dismiss the overlay, then retry.",
    "element_not_found": "Element refs are re-numbered after every page change. Observe the page and use a fresh ref.",
    "validation": "The input was rejected. Read the error message on the page and correct the value format "
                  "(dates for date inputs must be YYYY-MM-DD).",
    "auth": "Authentication is required or the session expired. Sign in again (credentials via {{secret:...}}).",
    "download": "That link is a document download. Use read_document with its URL instead.",
    "policy": "The runtime policy blocked this action. Do not retry it; choose another approach or ask the user.",
    "grounding": "Some values you are about to submit do not appear in anything you observed. Re-open the source "
                 "document/page, compare every field character by character, correct the form, then submit again.",
    "rejected": "The operator rejected this action. Respect the reason given; adjust or ask the user.",
    "unknown": "Unexpected error. Observe the current state before deciding the next step.",
}


def classify(message: str) -> str:
    for kind, pattern in RULES:
        if pattern.search(message or ""):
            return kind
    return "unknown"


def hint(kind: str) -> str:
    return HINTS.get(kind, HINTS["unknown"])
