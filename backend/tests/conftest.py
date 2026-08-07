"""Test environment setup. Sets required settings via env vars before any
app import triggers `Settings()` instantiation, so tests never need a real
Postgres/Qdrant/MinIO/Redis connection for pure unit-level logic."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/test")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
