import os
import sys
from pathlib import Path

# Isolated data dir + a dedicated sandbox port so tests never touch a running dev instance.
os.environ.setdefault("ATLAS_DATA_DIR", str(Path(__file__).parent / ".data"))
os.environ.setdefault("SANDBOX_PORT", "8011")
os.environ.setdefault("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", "test-key"))

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
