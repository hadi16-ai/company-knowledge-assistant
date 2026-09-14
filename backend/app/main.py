"""FastAPI application entrypoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import SessionLocal
from app.rag.vectorstore import get_qdrant_client
from app.storage.s3 import get_s3_client

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Enterprise AI Knowledge Platform API",
    version="2.0.0",
    description="FastAPI backend for the Company Knowledge Assistant — RAG over company documents.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Liveness probe used by Docker/Nginx/monitoring."""
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def readiness_check() -> dict[str, str] | JSONResponse:
    """Confirm that the API's required backing services are reachable.

    This deliberately does not create buckets, collections, or records: a
    monitoring probe must be safe to call repeatedly and must not mutate data.
    Internal exception details stay in server logs rather than being exposed to
    an unauthenticated caller.
    """
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        get_qdrant_client().get_collections()
        get_s3_client().list_buckets()
        Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3).ping()
    except Exception:  # noqa: BLE001 - readiness needs a single safe failure response
        logger.exception("Readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable"})

    return {"status": "ready"}
