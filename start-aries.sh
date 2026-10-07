#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ ! -f "$ROOT_DIR/.env" ]]; then
    echo "Missing .env in the repo root. Add DISCORD_TOKEN and SEARXNG_SECRET there." >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker was not found. Install Docker Engine and the Compose plugin, then retry." >&2
    exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama was not found. Install Ollama, then retry." >&2
    exit 1
fi

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
    echo "Ollama is not responding. Start it with: sudo systemctl start ollama" >&2
    exit 1
fi

if ! ollama show gemma4:12b >/dev/null 2>&1; then
    echo "The gemma4:12b model is missing. Download it with: ollama pull gemma4:12b" >&2
    exit 1
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    python3 -m venv "$ROOT_DIR/.venv"
    "$VENV_PYTHON" -m pip install -r "$ROOT_DIR/requirements.txt"
fi

cd "$ROOT_DIR"
docker compose up -d searxng

cd "$ROOT_DIR/discord-bot"
exec "$VENV_PYTHON" main.py
