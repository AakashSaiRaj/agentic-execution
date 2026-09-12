"""Application configuration.

All configuration is driven by environment variables (optionally loaded from a
`.env` file) so the same image/code runs unchanged across local, container and
CI environments.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General -----------------------------------------------------------
    app_name: str = "AI Agent Execution Platform"
    environment: str = "development"
    log_level: str = "INFO"

    # --- Database ----------------------------------------------------------
    # Defaults to a local SQLite file so the app runs with zero external
    # dependencies. Point this at Postgres for a production-style setup, e.g.
    #   postgresql+psycopg2://agent:agent@localhost:5432/agent_platform
    database_url: str = "sqlite:///./app.db"

    # --- LLM provider ------------------------------------------------------
    # One of: mock | openai | anthropic. "mock" needs no API key and lets the
    # whole pipeline run offline.
    llm_provider: str = "mock"
    llm_model: str = "mock-model"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # --- Planner -----------------------------------------------------------
    planner_min_tasks: int = 2
    planner_max_tasks: int = 5

    # --- Execution mode / distributed workers (Phase 2) --------------------
    # "inline"  -> plan + execute sequentially in a FastAPI background task
    #              (Phase 1 behaviour, no Redis required).
    # "queue"   -> enqueue jobs to Redis; separate worker processes execute
    #              tasks concurrently (Phase 2).
    execution_mode: str = "inline"
    redis_url: str = "redis://localhost:6379/0"
    # Number of concurrent consumer loops a single worker process runs.
    worker_concurrency: int = 4
    # Blocking dequeue timeout (seconds); also how often workers check for shutdown.
    worker_poll_timeout: int = 5

    # --- CORS --------------------------------------------------------------
    # Comma-separated list of allowed origins, or "*" for all.
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if raw == "*" or raw == "":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
