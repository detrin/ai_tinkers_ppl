"""AG-UI endpoint for the Trip Agent.

Lets `apps/channel` and `apps/web` plug in via `HttpAgent` from
`@ag-ui/client` -- the swap-out path already documented in
`packages/agent-core/src/agent.ts` -- instead of a bespoke REST API.

Run with: `uv run uvicorn agent.api:app`
"""

from __future__ import annotations

from pydantic_ai.ui.ag_ui import AGUIAdapter
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .config import Settings
from .trip_agent import TripAgent

trip_agent = TripAgent(Settings.from_env())


async def run_agent(request: Request) -> Response:
    return await AGUIAdapter.dispatch_request(request, agent=trip_agent.agent)


app = Starlette(routes=[Route("/", run_agent, methods=["POST"])])
