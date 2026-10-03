"""Central configuration. Everything tunable lives here and can be overridden via environment / .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = Path(os.getenv("ATLAS_DATA_DIR", BACKEND_DIR / "data"))
RUNS_DIR = DATA_DIR / "runs"            # per-run screenshots / artifacts
WORKSPACE_DIR = DATA_DIR / "workspace"  # sandboxed file area the agent may write to
ATLAS_DB = DATA_DIR / "atlas.db"        # runs, events, skills
SANDBOX_DB = DATA_DIR / "sandbox.db"    # simulated company systems
ATTACHMENTS_DIR = DATA_DIR / "attachments"

for _d in (DATA_DIR, RUNS_DIR, WORKSPACE_DIR, ATTACHMENTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- LLM ---------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
# Optional stronger model for planning + verification (defaults to the same model).
GEMINI_REASONING_MODEL = os.getenv("GEMINI_REASONING_MODEL", GEMINI_MODEL)
# USD per 1M tokens, used only for the live cost meter.
PRICE_INPUT_PER_M = float(os.getenv("PRICE_INPUT_PER_M", "0.30"))
PRICE_OUTPUT_PER_M = float(os.getenv("PRICE_OUTPUT_PER_M", "2.50"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "6"))

# --- Fallback providers (used only when every Gemini model is unavailable) -------
# Both are OpenAI-compatible. Model "auto" = discover a tool-capable model (OpenRouter: free models only).
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "auto")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "auto")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "auto")
OPENROUTER_VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL", "auto")

# --- Agent budgets -------------------------------------------------------------
MAX_STEPS = int(os.getenv("ATLAS_MAX_STEPS", "40"))
MAX_VERIFY_STEPS = int(os.getenv("ATLAS_MAX_VERIFY_STEPS", "14"))
MAX_AUTO_RETRIES = int(os.getenv("ATLAS_MAX_AUTO_RETRIES", "2"))
HEADLESS = os.getenv("ATLAS_HEADLESS", "1") != "0"

# --- Network -------------------------------------------------------------------
SANDBOX_HOST = os.getenv("SANDBOX_HOST", "127.0.0.1")
SANDBOX_PORT = int(os.getenv("SANDBOX_PORT", "8001"))
SANDBOX_URL = f"http://{SANDBOX_HOST}:{SANDBOX_PORT}"
API_PORT = int(os.getenv("ATLAS_API_PORT", "8000"))
# Hosts the http_get tool may call. The browser may visit the public web freely (read-only use).
HTTP_ALLOWLIST = [
    f"{SANDBOX_HOST}:{SANDBOX_PORT}",
    "en.wikipedia.org",
    "api.duckduckgo.com",
    "html.duckduckgo.com",
]
