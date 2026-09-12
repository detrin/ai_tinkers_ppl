# Shared backend tunnel (hackathon-local, no deployment)

`backend/` doesn't fit Vercel: it holds a WebSocket hub for live position sync
(Functions are request/response only, no long-lived server push) and its state
-- `GroupStore`, and `services/agent`'s conversation memory -- is in-process
memory, not a database. Deploying it properly means a persistent-process host
plus Postgres/Redis, which is real work we're deferring past the hackathon.

Instead: run `backend/` locally, and forward a stable public URL to it with a
named Cloudflare Tunnel. `frontend/` (once built) is served by the backend
itself at `/ui/` with relative asset paths and same-origin API calls -- see
`frontend/vite.config.ts` and `frontend/src/lib/api.ts` -- so the same tunnel
covers both with zero extra config.

**Public URL: `https://trip-planner.hermandaniel.com`**

## This is a baton pass, not shared hosting

Only **one machine** should have the backend + tunnel running at any given
moment. The tunnel forwards to `http://localhost:8000` on whoever's machine
is running `cloudflared` -- there's no shared database behind it, so if two
people ran it at once, Cloudflare would silently load-balance requests across
both, and each machine only knows about the groups created on itself. That's
the same class of bug the Slack `CHANNEL_CODE` multi-connection race was
(see `dev-docs/deploy.md`'s note on two runtimes racing one Channel) --
same root cause: one shared address point, two independent backing stores.

**Taking the baton:**

1. Confirm with whoever had it last that their `cloudflared` and backend are
   stopped (`pkill -f "cloudflared tunnel run"`, `pkill -f "uvicorn app.main:app"`).
2. `git pull`, and rebuild `frontend/` if it changed: `cd frontend && npm run build`.
3. Start the backend: `cd backend && PERSIST_STATE=0 .venv/bin/uvicorn app.main:app --port 8000`
4. Run the tunnel: `./scripts/tunnel.sh` (from repo root).

**Releasing it:** stop both processes, tell the next person.

## Getting `CLOUDFLARE_TUNNEL_TOKEN`

The token is a bearer credential for this tunnel -- ask Daniel for it
directly (Slack DM, not git) and add it to the repo-root `.env`:

```dotenv
CLOUDFLARE_TUNNEL_TOKEN=eyJ...
```

It is deliberately not committed here; `.env` is gitignored.

## Managing the tunnel itself

The tunnel (`trip-planner-backend`, id in Cloudflare's dashboard under
Zero Trust > Tunnels on the `hermandaniel.com` account) and its DNS record
are managed via the Cloudflare API, not `cloudflared tunnel create`. To
change where it points (e.g. a different port), update the tunnel's
ingress config:

```js
// via the Cloudflare MCP / API, not something scripted here
PUT /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations
{ "config": { "ingress": [
  { "hostname": "trip-planner.hermandaniel.com", "service": "http://localhost:8000" },
  { "service": "http_status:404" }
] } }
```

## When this is no longer needed

Delete the tunnel (revokes `CLOUDFLARE_TUNNEL_TOKEN` immediately, disconnects
any `cloudflared` still running with it) and its DNS record:

```js
DELETE /accounts/{account_id}/cfd_tunnel/{tunnel_id}
DELETE /zones/{zone_id}/dns_records/{trip-planner_record_id}
```

Ask Daniel to do this (or ask him to have an agent with Cloudflare access do
it) once the hackathon demo period is over -- don't leave a tunnel into
someone's laptop reachable indefinitely.
