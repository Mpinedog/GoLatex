#!/usr/bin/env bash
# GoLatex en macOS/Linux:  ./run.sh [carpeta-del-proyecto]
set -euo pipefail
cd "$(dirname "$0")"
PORT="${GOLATEX_PORT:-8123}"
if [ ! -x .venv/bin/python ]; then
  echo "Creando entorno virtual (.venv)..."
  python3 -m venv .venv
fi
STAMP=.venv/.requirements.sha256
HASH=$( (shasum -a 256 requirements.txt 2>/dev/null || sha256sum requirements.txt) | cut -d' ' -f1)
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$HASH" ]; then
  echo "Instalando dependencias..."
  .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
  echo "$HASH" > "$STAMP"
fi
if [ $# -gt 0 ]; then export GOLATEX_OPEN="$(cd "$1" && pwd)"; fi
( for _ in $(seq 40); do
    curl -sf "http://localhost:$PORT/api/state" >/dev/null && break; sleep 0.5
  done
  (open "http://localhost:$PORT" || xdg-open "http://localhost:$PORT") >/dev/null 2>&1 ) &
echo "GoLatex en http://localhost:$PORT  (Ctrl+C para cerrar)"
exec .venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port "$PORT"
