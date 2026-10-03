"""Secrets vault. The model only ever sees secret *names*; it writes `{{secret:name}}` in a typed value and the
tool layer substitutes the real value at the last moment. Values are scrubbed from every tool output too.
"""
from __future__ import annotations

import json
import os
import re

from config import DATA_DIR

SECRET_RE = re.compile(r"\{\{\s*secret:([a-zA-Z0-9_\-]+)\s*\}\}")

# Sandbox-only credentials for the fictional Globex portal. Real deployments would back this with a KMS.
DEFAULT_SECRETS = {
    "globex_portal_username": ("northwind-ap", "Username for the Globex billing portal"),
    "globex_portal_password": ("Gl0bex!Sandbox-2026", "Password for the Globex billing portal"),
}


class Vault:
    def __init__(self) -> None:
        self._secrets: dict[str, tuple[str, str]] = dict(DEFAULT_SECRETS)
        path = DATA_DIR / "vault.json"
        if path.exists():
            for name, entry in json.loads(path.read_text()).items():
                self._secrets[name] = (entry["value"], entry.get("description", ""))
        for key, value in os.environ.items():
            if key.startswith("ATLAS_SECRET_"):
                self._secrets[key.removeprefix("ATLAS_SECRET_").lower()] = (value, "from environment")

    def catalog(self) -> list[dict[str, str]]:
        return [{"name": n, "description": d} for n, (_, d) in self._secrets.items()]

    def has_placeholder(self, text: str) -> bool:
        return bool(SECRET_RE.search(text or ""))

    def resolve(self, text: str) -> str:
        def sub(m: re.Match) -> str:
            name = m.group(1)
            if name not in self._secrets:
                raise KeyError(f"Unknown secret '{name}'. Available: {', '.join(self._secrets)}")
            return self._secrets[name][0]
        return SECRET_RE.sub(sub, text)

    def scrub(self, text: str) -> str:
        for name, (value, _) in self._secrets.items():
            if value and len(value) >= 4:
                text = text.replace(value, f"[secret:{name}]")
        return text
