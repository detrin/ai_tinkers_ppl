#!/usr/bin/env bash
# Run the shared Cloudflare Tunnel for somejoy.hermandaniel.com, forwarding
# to a locally-run backend (+ its /ui/-mounted frontend build).
#
# This is a baton-pass setup: only one machine should run this (and the
# backend it forwards to) at a time. See dev-docs/backend-tunnel.md before
# running this for the first time -- in particular, confirm with whoever had
# it last that they've stopped theirs.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [ -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
  echo "CLOUDFLARE_TUNNEL_TOKEN is not set." >&2
  echo "Get it from Daniel directly (not git) and add it to the repo-root .env." >&2
  exit 1
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is not installed. brew install cloudflared" >&2
  exit 1
fi

if ! curl -sf http://127.0.0.1:8000/health >/dev/null; then
  echo "Nothing answering on http://127.0.0.1:8000 -- start the backend first:" >&2
  echo "  cd backend && PERSIST_STATE=0 .venv/bin/uvicorn app.main:app --port 8000" >&2
  exit 1
fi

echo "Backend is up. Starting the tunnel -- somejoy.hermandaniel.com will point here."
exec cloudflared tunnel run --token "$CLOUDFLARE_TUNNEL_TOKEN"
