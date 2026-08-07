"""Aggregates all v1 API routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, chat, documents

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
