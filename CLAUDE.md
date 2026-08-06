# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

A Streamlit-based RAG (Retrieval-Augmented Generation) application for conversational Q&A over company PDF documents. Users upload PDFs → documents are chunked, embedded, and stored locally → questions are answered by Gemini using retrieved chunks as grounded context with source citations.

## Development Commands

```powershell
# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the application (hot-reloads on file save)
streamlit run app.py
```

**No build, test, or lint tooling exists.** There is no test suite, no `pyproject.toml`, and no CI pipeline. Edit files and Streamlit reloads.

## Environment Setup

Copy `.env.example` to `.env` and set `GEMINI_API_KEY`. The `GEMINI_MODEL` variable is optional (defaults to `gemini-3-flash-preview` in `backend/rag.py:15`).

## Architecture

**Two-phase pipeline:**

**Ingestion** (`backend/ingest.py` orchestrates): PDF upload → save to `data/uploads/` → `loaders.py` (PyPDFLoader) → `splitter.py` (1000-char chunks, 200-char overlap) → `embeddings.py` (HuggingFace `BAAI/bge-small-en-v1.5`, runs locally) → `vectorstore.py` (ChromaDB at `data/chroma_db/`, collection `company_documents`).

**Retrieval/Q&A** (`backend/rag.py`): User question → embed with same HuggingFace model → `retrieval.py` fetches top-4 chunks by similarity → `context.py` builds bounded context (max 12,000 chars) with labeled source references → raw HTTP POST to Gemini API → `RAGAnswer` dataclass returned to `app.py`.

**Key design choice**: Embeddings are fully local (HuggingFace, no API key). Only answer generation hits an external API (Gemini). This means ingestion works offline.

**Gemini integration** (`backend/rag.py`) uses raw `urllib` HTTP calls (not Google SDK). Temperature is 0.2, maxOutputTokens is 800, with a system instruction to answer only from supplied context.

## Key Data Structures

All inter-module data flows through dataclasses:
- `IngestResult` — per-file ingestion outcome (success/skip/failure + chunk count)
- `RetrievedDocument` — ChromaDB chunk + similarity score (0.0–1.0)
- `SourceCitation` — filename, page number (1-indexed), excerpt, score
- `RAGAnswer` — answer text + list of `SourceCitation`

Chunk metadata stored in ChromaDB: `source` (filename), `source_path` (full path), `page` (zero-indexed; display adds +1).

## Session & Caching

- `st.session_state` holds conversation history as `[{"role": "user"|"assistant", "content": str, "sources": [...]}]`
- `@st.cache_resource` caches the vectorstore/embedding client across rerenders; cache is explicitly cleared after successful ingestion via `get_cached_vectorstore.clear()`

## Duplicate Detection

Ingestion checks at two levels before processing: filesystem existence in `data/uploads/` and ChromaDB query for existing chunks with the same source filename. Both checks must pass to skip re-ingestion.

## Error Handling Pattern

Each module defines its own exception class (`PDFLoadError`, `EmbeddingError`, `VectorStoreError`, `RetrievalError`, `AnswerGenerationError`). Ingestion wraps all exceptions into `IngestResult` dataclass so the UI can display per-file status without crashing. Gemini errors print full details to console (visible in server logs).

## Path & Platform Notes

`app.py` uses `PureWindowsPath` for filename extraction from upload paths (Windows compatibility). `utils.py` defines all path constants (`PROJECT_ROOT`, `DATA_DIR`, `UPLOADS_DIR`, `CHROMA_DIR`) — import from there rather than constructing paths inline.
