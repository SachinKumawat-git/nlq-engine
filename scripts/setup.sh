#!/usr/bin/env bash
# One-command local setup (no Docker): clone -> working endpoint.
set -euo pipefail

echo "==> Creating virtualenv"
python3 -m venv .venv
source .venv/bin/activate

echo "==> Installing dependencies"
pip install --upgrade pip -q
pip install -r requirements.txt -q

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
fi

if command -v ollama >/dev/null 2>&1; then
  echo "==> Ollama found. Pulling qwen2.5-coder:7b-instruct (skips if already present)"
  ollama pull qwen2.5-coder:7b-instruct || echo "WARNING: could not pull model; is 'ollama serve' running?"
else
  echo "WARNING: 'ollama' CLI not found."
  echo "Install from https://ollama.com, then run: ollama pull qwen2.5-coder:7b-instruct"
  echo "Or set LLM_PROVIDER=openai_compatible in .env to use a hosted model instead."
fi

mkdir -p data/db data/uploads

echo "==> Starting API on http://localhost:8000"
uvicorn app.main:app --reload --port 8000
