"""FastAPI application entrypoint.

Wires together configuration, logging, CORS and the API routers. Routes are
mounted under the ``/api`` prefix (e.g. POST /api/executions) so the frontend
dev server can proxy a single path to the backend.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .logging_config import configure_logging, get_logger
from .api.routes import executions, health

configure_logging()
settings = get_settings()
logger = get_logger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Phase 1 MVP: decomposes a user task into subtasks, executes agents "
        "sequentially, and returns an aggregated result."
    ),
)

# CORS: when allowing all origins we must disable credentials per the CORS spec.
_allow_all_origins = settings.cors_origin_list == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=not _allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health is exposed both at the root (/health, used by container health checks)
# and under /api/health (convenient behind the frontend proxy).
app.include_router(health.router)
app.include_router(health.router, prefix="/api")
app.include_router(executions.router, prefix="/api")


@app.get("/", tags=["root"], summary="Service information")
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
        "api": {
            "create_execution": "POST /api/executions",
            "get_execution": "GET /api/executions/{id}",
            "list_execution_tasks": "GET /api/executions/{id}/tasks",
            "list_executions": "GET /api/executions",
        },
    }


@app.on_event("startup")
def on_startup() -> None:
    logger.info(
        "%s v%s starting (env=%s, llm_provider=%s, db=%s)",
        settings.app_name,
        __version__,
        settings.environment,
        settings.llm_provider,
        settings.database_url.split("://", 1)[0],
    )
