"""Runtime configuration, read once from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # --- AI ranking -----------------------------------------------------
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY") or None
    )
    anthropic_model: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-opus-5")
    )

    # --- Place discovery (keyless) ---------------------------------------
    overpass_url: str = field(
        default_factory=lambda: os.getenv(
            "OVERPASS_URL", "https://overpass-api.de/api/interpreter"
        )
    )
    nominatim_url: str = field(
        default_factory=lambda: os.getenv(
            "NOMINATIM_URL", "https://nominatim.openstreetmap.org"
        )
    )
    # Nominatim's usage policy requires a real, identifying User-Agent.
    user_agent: str = field(
        default_factory=lambda: os.getenv(
            "NOMINATIM_USER_AGENT", "citygroup-router/0.1 (set NOMINATIM_USER_AGENT)"
        )
    )

    # --- Routing ---------------------------------------------------------
    # Preference order at runtime: OpenRouteService -> OSRM -> straight-line.
    ors_api_key: str | None = field(
        default_factory=lambda: os.getenv("ORS_API_KEY") or None
    )
    ors_url: str = field(
        default_factory=lambda: os.getenv("ORS_URL", "https://api.openrouteservice.org")
    )
    osrm_url: str | None = field(
        default_factory=lambda: os.getenv("OSRM_URL", "https://router.project-osrm.org")
        or None
    )
    # The public OSRM demo server only serves the car profile.
    osrm_profile: str = field(
        default_factory=lambda: os.getenv("OSRM_PROFILE", "driving")
    )
    walking_speed_kmh: float = field(
        default_factory=lambda: float(os.getenv("WALKING_SPEED_KMH", "4.8"))
    )

    # --- Behaviour -------------------------------------------------------
    search_radius_m: int = field(
        default_factory=lambda: int(os.getenv("SEARCH_RADIUS_M", "4000"))
    )
    max_candidates: int = field(
        default_factory=lambda: int(os.getenv("MAX_CANDIDATES", "350"))
    )
    http_timeout_s: float = field(
        default_factory=lambda: float(os.getenv("HTTP_TIMEOUT_S", "45"))
    )
    state_file: Path | None = field(
        default_factory=lambda: (
            Path(os.getenv("STATE_FILE", "state.json"))
            if _flag("PERSIST_STATE", True)
            else None
        )
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "*").split(",")
            if o.strip()
        )
    )

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
