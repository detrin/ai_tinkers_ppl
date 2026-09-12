"""Group city-route backend.

Run it with:  uvicorn app.main:app --reload
Docs at:      http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import groups, realtime
from .services import http

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)
log = logging.getLogger("citygroup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "AI ranking: %s | routing: %s",
        "on" if settings.ai_enabled else "off (heuristic fallback)",
        "openrouteservice"
        if settings.ors_api_key
        else ("osrm" if settings.osrm_url else "straight-line"),
    )
    yield
    await http.close()


app = FastAPI(
    title="Group City Route",
    version="0.1.0",
    description=(
        "Scans a city for places worth visiting, picks the ones a group will "
        "like, orders them into a walking route, and keeps everyone's live "
        "position in sync."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(groups.router)
app.include_router(realtime.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "ai_ranking": settings.ai_enabled,
        "model": settings.anthropic_model if settings.ai_enabled else None,
        "routing": (
            "openrouteservice"
            if settings.ors_api_key
            else ("osrm" if settings.osrm_url else "straight-line")
        ),
        "places": "overpass",
        "geocoder": "nominatim",
    }
