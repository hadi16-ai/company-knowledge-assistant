# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

An Enterprise AI Knowledge Platform: a FastAPI + Next.js RAG (Retrieval-Augmented Generation) application for conversational Q&A over company PDF documents. Users upload PDFs → an async Celery worker chunks, embeds, and stores them in Qdrant → questions are answered by Gemini (streamed over SSE) using retrieved chunks as grounded context with source citations. This is v2, rebuilt from a Streamlit prototype per [`ARCHITECTURE_REVIEW.md`](./ARCHITECTURE_REVIEW.md), which remains the source of truth for the overall multi-phase roadmap — consult it before making architectural changes.

## Development Commands

```bash
# Configure environment (one-time)
cp backend/.env.example backend/.env
# then set GEMINI_API_KEY and JWT_SECRET_KEY in backend/.env

# Run the full stack (Postgres, Qdrant, MinIO, Redis, API, worker, web)
docker-compose up --build
```

- API: http://localhost:8000 (Swagger docs at `/docs`)
- Web: http://localhost:3000

No Docker? You can run pieces natively for backend-only iteration: `pip install -r backend/requirements.txt`, point `DATABASE_URL`/`QDRANT_URL`/`S3_ENDPOINT_URL`/`REDIS_URL` at real instances, then `uvicorn app.main:app --reload` (from `backend/`) and `celery -A app.workers.celery_app worker -Q ingestion` in a second terminal. For the frontend: `cd frontend && npm run dev`.

**Testing/linting:** `cd backend && pytest`. `cd frontend && npm run lint && npm run build`. No CI pipeline exists yet (Phase 2).

## Architecture

**Two-phase pipeline, same shape as v1, now async and multi-tenant-ready:**

**Ingestion** (`backend/app/api/v1/documents.py` → `backend/app/workers/tasks.py`): PDF upload → validate type/size → store in MinIO (`orgs/{org_id}/docs/{doc_id}/{filename}`) → create `documents` row (status `pending`) → enqueue Celery task → return 202 immediately. The worker downloads the file, runs `rag/loaders.py` (PyPDFLoader) → `rag/splitter.py` (1000-char chunks, 200-char overlap) → `rag/embeddings.py` (HuggingFace `BAAI/bge-small-en-v1.5`, local) → `rag/vectorstore.py` (Qdrant, collection `{prefix}_{org_id}`), then updates the `documents` row to `ready`/`failed`.

**Retrieval/Q&A** (`backend/app/api/v1/chat.py` → `backend/app/rag/rag.py`): question → `rag/retrieval.py` fetches top-k chunks from the caller's org Qdrant collection → `rag/context.py` builds bounded context (default 12,000 chars) with labeled source references → `google-generativeai` SDK streams the answer over SSE (`/chat/ask`) → each turn is logged to the `query_log` table.

**Key design choices carried over from v1:** embeddings are fully local (HuggingFace, no API key) so ingestion works without external calls beyond MinIO/Postgres/Qdrant; only answer generation hits Gemini.

**What changed from v1:** ChromaDB → Qdrant (one collection per org); local disk uploads → MinIO; synchronous ingestion → Celery/Redis async; raw `urllib` Gemini calls → the official SDK with native streaming; no auth → JWT access/refresh tokens with Admin/Employee roles; Streamlit → FastAPI + Next.js.

## Key Data Structures

- `app/db/models.py` — SQLAlchemy ORM: `Organization`, `User`, `Document`, `QueryLog`. Every table keys to `org_id`; Phase 1 runs a single seeded organization (`app/db/seed.py`), full row-level multi-tenancy is Phase 2.
- `app/rag/context.py::SourceCitation` — filename, page number (1-indexed; Qdrant metadata stores it 0-indexed), excerpt, score.
- `app/rag/rag.py::RAGAnswer` — non-streaming answer + citations, used by `/chat/ask-sync` and tests. The primary path (`/chat/ask`) streams tokens via `stream_answer_tokens()` instead.
- `app/schemas/*.py` — Pydantic request/response models for the API layer (kept separate from ORM models).

## Auth & Multi-Tenancy Notes

Every authenticated request carries `org_id` and `role` inside the JWT (`app/core/security.py`), decoded by `app/deps.py::get_current_user`. Handlers read `org_id` from there — **never** from request parameters — so a user cannot access another organization's data by editing an id in the request (see architecture review §6 IDOR note). This matters most in `app/rag/vectorstore.py`, where the org id selects the Qdrant collection name server-side.

## Error Handling Pattern

Each module still defines its own exception class (`PDFLoadError`, `EmbeddingError`, `VectorStoreError`, `RetrievalError`, `AnswerGenerationError`, `StorageError`). FastAPI routers catch these and translate to HTTP errors; the Celery task (`app/workers/tasks.py`) catches them and writes to `Document.error_message` / sets status `failed` instead of crashing the worker. Logging is structured JSON via `app/core/logging.py` (replaces v1's `print()` statements).

## Path & Platform Notes

Backend runs as a Linux container in Docker (no more `PureWindowsPath` workarounds). All backend config comes from `app/core/config.py::Settings` (pydantic-settings, reads `backend/.env`) — import from there rather than reading `os.environ` directly. Frontend config is `NEXT_PUBLIC_API_URL` (see `frontend/.env.local.example`).
