from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Pydantic AI reads provider credentials straight from the environment
# (OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, ...) when given a
# 'provider:model' string, so extend this alongside a real need rather than
# guessing ahead.
_PROVIDER_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


def _load_repo_env() -> None:
    """Load the repo-root `.env`, shared across all apps and services."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.exists():
            load_dotenv(candidate)
            return


def _resolve_model_id(provider: str, model: str) -> str:
    env_var = _PROVIDER_ENV_VARS.get(provider)
    if env_var is None:
        raise RuntimeError(
            f"Unsupported MODEL_PROVIDER '{provider}' for the Trip Agent; "
            "add it to _PROVIDER_ENV_VARS in agent/config.py before using it here."
        )
    if not os.environ.get(env_var):
        raise RuntimeError(f"{env_var} is not set. Configure it in the repo root .env.")
    return f"{provider}:{model}"


@dataclass(frozen=True)
class Settings:
    model_id: str
    exa_api_key: str | None
    exa_search_type: str
    google_maps_api_key: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        _load_repo_env()
        os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

        # AGENT_MODEL_PROVIDER/AGENT_MODEL let this service pin its own model
        # independently of the shared MODEL_PROVIDER/MODEL that apps/channel
        # and apps/web use, falling back to those when unset.
        provider = (
            os.environ.get("AGENT_MODEL_PROVIDER")
            or os.environ.get("MODEL_PROVIDER", "openai")
        ).strip().lower()
        model = os.environ.get("AGENT_MODEL") or os.environ.get("MODEL", "gpt-4o-mini")

        return cls(
            model_id=_resolve_model_id(provider, model),
            exa_api_key=os.environ.get("EXA_API_KEY") or None,
            exa_search_type=os.environ.get("EXA_SEARCH_TYPE", "fast"),
            google_maps_api_key=os.environ.get("GOOGLE_MAPS_API_KEY") or None,
        )
