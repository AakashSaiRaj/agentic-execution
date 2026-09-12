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

    # --- Reliability (Phase 3) --------------------------------------------
    # Maximum retries after the first attempt (total tries = max_retries + 1).
    task_max_retries: int = 3
    # Hard timeout for a single task execution.
    task_timeout_seconds: float = 30.0
    # Exponential backoff between retries: delay = base * 2**(attempt-1), capped.
    retry_backoff_base_seconds: float = 1.0
    retry_backoff_max_seconds: float = 30.0
    retry_backoff_jitter: bool = True
    # A RUNNING task not updated within this window is treated as crashed and
    # recovered (re-queued or failed). Should exceed task_timeout_seconds.
    task_lease_seconds: float = 90.0
    # How often the worker's reaper scans for stale RUNNING tasks.
    recovery_interval_seconds: float = 15.0
    # How often the worker promotes due delayed (retry) tasks to the queue.
    delayed_poll_interval_seconds: float = 1.0

    # --- Server-Sent Events (Phase 3) -------------------------------------
    sse_poll_interval_seconds: float = 0.75
    sse_max_seconds: int = 600

    # --- Tools (Phase 4) ---------------------------------------------------
    tools_enabled: bool = True
    tool_timeout_seconds: float = 10.0
    agent_max_tool_iterations: int = 3
    fetch_max_bytes: int = 20000  # cap for the URL fetch tool

    # --- Security / limits (Phase 5) --------------------------------------
    # API key auth. If BOTH are empty, auth is DISABLED (dev-friendly). Set one
    # in production. Multiple keys may be supplied comma-separated in api_keys.
    api_key: Optional[str] = None
    api_keys: str = ""
    # Requests per minute per client (API key or IP). 0 disables rate limiting.
    rate_limit_per_minute: int = 0
    # Reject request bodies larger than this many bytes (413).
    max_request_bytes: int = 65536
    # uvicorn worker processes (read by the container entrypoint).
    uvicorn_workers: int = 1

    @property
    def configured_api_keys(self) -> list[str]:
        keys = []
        if self.api_key:
            keys.append(self.api_key.strip())
        keys.extend(k.strip() for k in (self.api_keys or "").split(",") if k.strip())
        return [k for k in keys if k]

    # --- Logging format ----------------------------------------------------
    log_format: str = "text"  # text | json

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
