#!/usr/bin/env bash
# Atlas - one-command setup + start (macOS / Linux).  ./run.sh [--dev]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
[ -f "$ROOT/.env" ] || { cp "$ROOT/.env.example" "$ROOT/.env"; echo "Created .env - add your GEMINI_API_KEY"; }
PY="$ROOT/backend/.venv/bin/python"
if [ ! -x "$PY" ]; then
  python3 -m venv "$ROOT/backend/.venv"
  "$PY" -m pip install -q -r "$ROOT/backend/requirements.txt"
  "$PY" -m playwright install chromium
fi
[ -d "$ROOT/frontend/node_modules" ] || (cd "$ROOT/frontend" && npm install)
if [ "${1:-}" = "--dev" ]; then
  (cd "$ROOT/backend" && "$PY" -m app.main) &
  cd "$ROOT/frontend" && npm run dev
else
  (cd "$ROOT/frontend" && npm run build)
  echo "Atlas on http://127.0.0.1:8000  (sandbox apps on http://127.0.0.1:8001)"
  cd "$ROOT/backend" && "$PY" -m app.main
fi
