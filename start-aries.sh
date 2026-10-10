#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ ! -f "$ROOT_DIR/.env" ]]; then
    echo "Missing the repo-root .env required by SearXNG. Set SEARXNG_SECRET there; bot credentials can be in discord-bot/.env." >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker was not found. Install Docker Engine and the Compose plugin, then retry." >&2
    exit 1
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    python3 -m venv "$ROOT_DIR/.venv"
    "$VENV_PYTHON" -m pip install -r "$ROOT_DIR/requirements.txt"
fi

cd "$ROOT_DIR"
docker compose up -d searxng

cd "$ROOT_DIR/discord-bot"
exec "$VENV_PYTHON" -u main.py
