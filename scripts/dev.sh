#!/usr/bin/env bash
# Run the whole stack locally: Supabase (Docker), engine API (:8000) and web app (:5173).
# Usage: bash scripts/dev.sh            Ctrl-C stops the API and the web app;
#        npx supabase stop               stops the database containers (data is kept).
# Guide: docs/local-setup.md
set -euo pipefail
cd "$(dirname "$0")/.."

need() { command -v "$1" >/dev/null || { echo "missing: $1 ($2)"; exit 1; }; }
need docker "install Docker Desktop and start it"
need node "install Node 22: brew install node@22"
need pnpm "enable it with: corepack enable"
need uv "install it with: brew install uv"
docker info >/dev/null 2>&1 || { echo "Docker is not running: open Docker Desktop first"; exit 1; }

# Google sign-in (optional): supabase/.env.local, see supabase/.env.example (the CLI loads it)
echo "▸ Supabase (first run downloads the images, a few minutes)"
npx --yes supabase@2 start
bash scripts/local-env.sh

echo "▸ Dependencies"
uv sync --quiet
(cd web && pnpm install --silent)

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "▸ API on http://localhost:8000"
uv run --package atsurvey-api uvicorn atsurvey_api.main:app --reload --reload-dir api/src --reload-dir engine/src --port 8000 &
pids+=($!)

echo "▸ Web app on http://localhost:5173"
(cd web && exec pnpm dev --port 5173 --strictPort) &
pids+=($!)

cat <<MSG

  App        http://localhost:5173
  Emails     http://127.0.0.1:54324   (sign-up confirmations land here)
  Database   http://127.0.0.1:54323   (Supabase Studio)
  Ctrl-C to stop the API and the app.

MSG
wait
