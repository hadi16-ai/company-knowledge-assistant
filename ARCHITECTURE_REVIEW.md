# Enterprise AI Knowledge Platform — Architecture Review

**Principal AI Architect Review · August 2026**

A complete architecture review of the current Company Knowledge Assistant codebase, followed by a Version 2 design for a production-grade Enterprise AI Knowledge Platform.

---

## Table of Contents

1. [Current Architecture Review](#1-current-architecture-review)
2. [Technology Stack](#2-technology-stack)
3. [Permanent Document Storage](#3-permanent-document-storage)
4. [Production RAG Pipeline](#4-production-rag-pipeline)
5. [UI / UX](#5-ui--ux)
6. [Authentication & RBAC](#6-authentication--rbac)
7. [Multi-Tenant Architecture](#7-multi-tenant-architecture)
8. [AI Improvements](#8-ai-improvements)
9. [Scalability](#9-scalability)
10. [Deployment](#10-deployment)
11. [Enterprise Features](#11-enterprise-features)
12. [Prioritization Roadmap](#12-prioritization-roadmap)

---

## 1. Current Architecture Review

The existing implementation is a well-structured prototype. The modular backend, typed dataclasses, and local embedding design all show the right instincts. What it lacks is everything required to run in a company: persistence, auth, multi-user isolation, and production-grade retrieval. None of these are hard to fix — they just weren't the goal for v1.

### Strengths — Keep

- Clean module boundaries — each concern isolated in its own file
- Dataclass-based data flow (`IngestResult`, `RAGAnswer`) — typed and predictable
- Local embeddings (`BAAI/bge-small-en-v1.5`) — zero ingestion API cost, offline-capable
- Two-level duplicate detection — filesystem + vector store
- Per-file error wrapping — UI never crashes on bad PDFs
- Streamlit cache clear after ingestion — correct cache invalidation pattern

### Weaknesses — Must Fix

- Streamlit: single-user, no real routing, can't build proper auth flows
- Local filesystem storage — documents vanish on every redeploy
- ChromaDB on local disk — not shared across processes or machines
- No conversation memory — every question is completely stateless
- Simple top-4 retrieval — no reranking, no hybrid search
- Raw `urllib` to Gemini — no retry, no timeout, no streaming
- No authentication at any level

### Technical Debt

- `PureWindowsPath` in `app.py` — breaks on Linux/Mac deployments
- `print()` statements throughout — no structured logging
- Default model `gemini-3-flash-preview` — nonstandard name, may not be valid
- No file type or MIME validation on upload — security gap
- Hardcoded constants in `rag.py` — temperature, maxOutputTokens not configurable

### Bottlenecks

- Embedding model cold-start on every server restart (15–30s)
- Synchronous PDF processing blocks the UI during upload
- No query result caching — identical questions re-embed and re-retrieve
- Single-threaded; no async anywhere in the pipeline
- Entire ChromaDB collection scanned per query (no metadata pre-filter)

> **Verdict:** The architecture pattern is sound — ingestion pipeline, retrieval pipeline, and UI separation are correctly identified. What needs to change is the infrastructure underneath: replace the local-only storage, add an async processing layer, and swap Streamlit for a real frontend framework. The backend Python logic can largely be preserved and migrated to FastAPI.

---

## 2. Technology Stack

The guiding principle: stay in Python for the backend (preserves your ML ecosystem), go with the industry-standard React stack for the frontend, and pick infrastructure that is self-hostable but can scale to managed cloud when needed.

### Decisions

| Layer | Choice | Decision | Reasoning |
|---|---|---|---|
| Frontend | Next.js 14 (App Router) + React | **Replace Streamlit** | Proper routing, SSR, streaming support, industry standard. Streamlit cannot build enterprise auth flows or a professional chat UI. |
| UI Components | shadcn/ui + Tailwind CSS | **New** | Radix UI primitives (accessible), beautiful defaults, copy-paste components. You own the code. Every enterprise UI pattern is included. |
| Backend API | FastAPI | **New** | Async by default — critical for I/O-heavy RAG. Auto-generated OpenAPI docs. Pydantic models align with your existing dataclasses. |
| Embeddings | BAAI/bge-small-en-v1.5 (local) | **Keep** | Excellent quality-to-size ratio. 384 dimensions, fast inference, runs on CPU. No API cost. One of the best choices in v1. |
| LLM | Gemini API via official SDK | **Upgrade** | Replace raw `urllib` with `google-generativeai` SDK. Gets retry logic, proper error types, and streaming support for free. |
| Vector DB | Qdrant | **Replace ChromaDB** | Self-hostable, payload filtering, named vectors, Rust-backed performance. One Docker command. ChromaDB doesn't scale beyond a single process. |
| Primary DB | PostgreSQL 16 | **New** | Users, organizations, documents, collections, audit logs. ACID, row-level security for multi-tenancy. |
| File Storage | MinIO (S3-compatible) | **Replace local disk** | Self-hostable, S3-compatible API so you can swap to AWS S3 without code changes. Documents survive redeploys. |
| Task Queue | Celery + Redis | **New** | PDF processing must be async — you can't block the HTTP request for 30s while chunking and embedding. |
| Auth | JWT (FastAPI) + Clerk or Auth.js | **New** | Clerk has built-in org management and is free to start. Auth.js gives more control. |
| Icons | Lucide React | **New** | Clean, consistent, tree-shakeable. The standard pairing with shadcn/ui. |
| Charts | Tremor | **New** | Purpose-built for dashboards, Tailwind-native. |

### Target Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│  CLIENT          Next.js Web App                            │
├─────────────────────────────────────────────────────────────┤
│  API GATEWAY     FastAPI REST  │  WebSocket (streaming)     │
│                  Nginx reverse proxy                        │
├─────────────────────────────────────────────────────────────┤
│  SERVICES        RAG Engine  │  Doc Processor  │  Auth      │
│                  Analytics Service                          │
├─────────────────────────────────────────────────────────────┤
│  ASYNC WORKERS   Celery Workers  │  Redis Queue             │
├─────────────────────────────────────────────────────────────┤
│  DATA            PostgreSQL  │  Qdrant  │  MinIO/S3  │Redis │
├─────────────────────────────────────────────────────────────┤
│  EXTERNAL        Gemini API  │  HuggingFace (local)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Permanent Document Storage

Document permanence requires separating three distinct concerns that are currently tangled together: raw files, structured metadata, and vector representations. Each requires a different storage system.

### Storage Architecture

| Layer | System | Details |
|---|---|---|
| Raw Files | MinIO / AWS S3 | Path: `orgs/{org_id}/docs/{doc_id}/original.pdf` · Versioned uploads · Presigned URLs for download |
| Metadata | PostgreSQL | Organizations, users, documents, collections · Document status (ingesting / ready / failed) · Audit log |
| Vectors | Qdrant | One collection per organization: `org_{uuid}` · Payload: source, page, section, doc_id, org_id · Payload filtering before ANN search |

### Vector Database Comparison

| Database | Self-hostable | Multi-tenant | Hybrid search | Payload filter | Production-ready | Verdict |
|---|---|---|---|---|---|---|
| ChromaDB | ✓ | ✗ | ✗ | Partial | No — SQLite-backed, single process | Dev / prototype only |
| **Qdrant** | ✓ | ✓ | ✓ | ✓ | Yes — Rust, HNSW, gRPC | **Best for self-hosted** |
| Pinecone | ✗ | ✓ | ✓ | ✓ | Yes — fully managed | Best for cloud-only, no ops |
| Weaviate | ✓ | Partial | ✓ | ✓ | Yes — but complex to operate | Good if you need GraphQL |

> **Recommendation:** Use **Qdrant** for V2. It runs as a single Docker container, supports the payload filtering needed for multi-tenant isolation, and has a cloud offering when you want to move off self-hosted. Pinecone is the right call only if you want zero infrastructure ownership from day one.

### Core PostgreSQL Tables

| Table | Key columns | Purpose |
|---|---|---|
| organizations | id, name, slug, plan, created_at | Tenant root — every other record keys to this |
| users | id, org_id, email, role, last_active | Employee accounts with role assignment |
| documents | id, org_id, filename, storage_path, status, chunk_count, created_by | Document registry with ingestion status |
| collections | id, org_id, name, description | Logical groupings: HR, Legal, Technical, etc. |
| query_log | id, org_id, user_id, query, answer, latency_ms, created_at | Analytics, audit trail, quality monitoring |

---

## 4. Production RAG Pipeline

The v1 pipeline (embed → top-4 similarity → send to LLM) works for demos. It fails in production because it misses exact keyword matches, has no way to recover from a bad query, and returns results with no confidence signal. The v2 pipeline adds hybrid search, reranking, and conversation memory — the three improvements with the highest ROI.

### Ingestion Pipeline

```
Phase 1 — Upload & Queue
─────────────────────────────────────────────────────────────
File Upload → Validate (type, size, MIME) → Store to S3 (MinIO/AWS)
           → Queue Job (Celery + Redis) → Return 202 (async)

Phase 2 — Processing Workers (Async, non-blocking)
─────────────────────────────────────────────────────────────
OCR Check (scanned PDF?) → Extract Text (+ tables) → Clean (fix encoding,
strip headers) → Semantic Chunk (section-aware) → Enrich Metadata
(section, author, date) → Batch Embed (BGE local) → Store Qdrant
(+ update PostgreSQL) → Notify (WebSocket)
```

### Query & Retrieval Pipeline

```
Pre-Retrieval
─────────────────────────────────────────────────────────────
User Query → Inject Memory (last 5 turns) → Query Rewrite
          (expand jargon, fix typos) → Apply Filters (org_id + collection)

Hybrid Retrieval — Both branches run in parallel
─────────────────────────────────────────────────────────────
Dense Vector Search (BGE embeddings, top 20) ──┐
                                                ├→ RRF Merge → Cross-Encoder Rerank
BM25 Sparse Search (keyword match, top 20) ────┘    (top 20 → 5)     → Context Compress

Generation
─────────────────────────────────────────────────────────────
Build Prompt (context + citations) → Gemini API (stream response)
→ Extract Citations → Confidence Score → Log + Stream to client (SSE)
```

### Key Technique Decisions

- **Semantic chunking over fixed-size:** Your current `splitter.py` uses 1000-char fixed chunks. Semantic chunking splits on headings, paragraphs, and sentence boundaries — chunks mean something, rather than cutting mid-sentence.

- **Hybrid search (BM25 + dense):** Dense vectors miss exact keyword matches. If an employee asks about "ISO 9001:2015 clause 8.4", BM25 finds it instantly. Combining both via Reciprocal Rank Fusion (RRF) is the single highest-ROI improvement you can make.

- **Cross-encoder reranking:** Use `ms-marco-MiniLM-L-6-v2` from sentence-transformers. It scores query-document pairs directly (not separately like bi-encoders), dramatically improving relevance. Run it only on the top 20 from retrieval — never the whole collection.

- **Conversation memory:** Inject the last 5 turns as context before rewriting. Without this, "What does that section say?" has no referent. This is table stakes for any enterprise product.

- **Metadata filtering:** Qdrant payload filters scope the ANN search to the correct organization and collection *before* any vector math happens. This is both a security requirement and a performance win.

---

## 5. UI / UX

### Recommended Stack

| Layer | Choice | Reasoning |
|---|---|---|
| Framework | Next.js 14 App Router | Parallel route loading, streaming via SSE, proper layout nesting |
| Components | shadcn/ui | Copy-paste Radix UI components. You own the code. Accessible by default. |
| Styling | Tailwind CSS | Pairs with shadcn/ui natively. Dark mode via `dark:` variants. |
| Icons | Lucide React | Consistent, tree-shakeable, 1,400+ icons |
| Charts | Tremor | Purpose-built dashboards, Tailwind-native |
| Animation | Framer Motion (minimal) | Only for message appear + source panel slide-in. Don't over-animate enterprise software. |

### Application Screens

| Route | Screen | Key elements |
|---|---|---|
| /login | Authentication | Clean centered form, SSO button, organization subdomain support |
| /dashboard | Home Dashboard | Stat cards (documents, queries, users), recent queries, quick-start actions |
| /chat | Chat Interface | Left sidebar (conversation history), main thread (streaming), right panel (source citations) |
| /chat/[id] | Conversation | Full conversation, export as PDF, share with colleague |
| /knowledge | Knowledge Base | Document library with search, filter by collection, upload status, bulk actions |
| /knowledge/upload | Upload | Drag-and-drop zone, multi-file progress, collection assignment |
| /admin | Admin Panel | User management, role assignment, collection management, API key generation |
| /analytics | Analytics | Query volume over time, popular documents, unanswered queries, response quality trend |
| /settings | Settings | Profile, notification preferences, connected integrations |

### Chat Interface — The Most Important Screen

- **Streaming responses** via Server-Sent Events — answer appears word by word, not after a 3s wait
- **Source citations** appear below each answer as expandable cards — filename, page number, excerpt
- **Confidence indicator** per answer (e.g., "Based on 3 sources — high confidence")
- **Thumbs up / down** feedback inline with each answer — feeds the improvement loop
- **Copy button** on answers — enterprise users paste answers into emails and reports
- **Dark mode** built-in via shadcn/ui — no extra work needed

---

## 6. Authentication & RBAC

### Role Hierarchy

```
                    ┌──────────────┐
                    │  Super Admin │  Platform-wide. Manages all orgs. Billing.
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │ Company Admin│  Full org control. All documents, users, settings.
                    └──────┬───────┘
                           │
             ┌─────────────┴─────────────┐
      ┌──────┴──────┐             ┌──────┴──────┐
      │   Manager   │             │  Employee   │
      │ Manages     │             │ Search and  │
      │ collections │             │ chat only   │
      └─────────────┘             └─────────────┘
                           │
                    ┌──────┴───────┐
                    │    Guest     │  Time-limited. Read-only on specific collections.
                    └──────────────┘
```

### Permission Matrix

| Action | Super Admin | Company Admin | Manager | Employee | Guest |
|---|---|---|---|---|---|
| Chat / Search | ✓ | ✓ | ✓ | ✓ | Limited |
| Upload documents | ✓ | ✓ | ✓ | ✗ | ✗ |
| Delete documents | ✓ | ✓ | ✗ | ✗ | ✗ |
| Manage users | ✓ | ✓ | ✗ | ✗ | ✗ |
| View analytics | ✓ | ✓ | ✓ | ✗ | ✗ |
| Create collections | ✓ | ✓ | ✓ | ✗ | ✗ |
| Access audit log | ✓ | ✓ | ✗ | ✗ | ✗ |
| Generate API keys | ✓ | ✓ | ✗ | ✗ | ✗ |

> **Implementation note:** Use short-lived JWT access tokens (15 min) + refresh tokens (7 days). The JWT payload carries `user_id`, `org_id`, and `role`. Every FastAPI route handler reads `org_id` from the token — the user never supplies it directly. This prevents IDOR attacks where a user changes an ID in the request to access another company's data.

---

## 7. Multi-Tenant Architecture

Multi-tenancy means Company A can never see Company B's documents, queries, or users — not even by accident, and not even if the code has a bug. Design the isolation at the data layer so a single missing `WHERE` clause cannot cause a breach.

### Three-Layer Isolation Model

**PostgreSQL**
- Every table has `org_id` column
- Row-Level Security (RLS) policies enabled
- Current org set via `SET app.current_org` per connection
- RLS enforces `org_id = current_org` automatically

**Qdrant**
- One collection per organization: `org_{uuid}`
- Payload filter on every query: `org_id = X`
- Collection names never exposed to frontend
- API middleware injects collection from JWT — not from request

**File Storage**
- Path prefix: `orgs/{org_id}/docs/{doc_id}/`
- Presigned URLs expire in 1 hour
- Bucket policy: service account only — no public access

**API Layer**
- JWT decoded to extract `org_id` before any handler runs
- Middleware injects org context into every downstream call
- API routes never accept `org_id` as a query parameter

### Collection-Level Permissions

Organizations can create multiple named collections — HR Policies, Technical Docs, Safety Manuals, etc. Users can be granted access to specific collections rather than all documents. A factory worker sees the safety manual but not the executive contracts. This requires a `user_collection_access` junction table in PostgreSQL and a collection filter injected alongside the org filter in every Qdrant query.

---

## 8. AI Improvements

Most AI techniques get discussed far more than they deserve. The table below rates each by ROI and effort, and gives a clear verdict. The goal is better answers, not a more complex pipeline.

| Technique | ROI | Effort | Verdict |
|---|---|---|---|
| Hybrid Search (BM25 + Dense) | High | Medium | **Build Now** |
| Cross-Encoder Reranking | High | Medium | **Build Now** |
| Conversation Memory | High | Low | **Build Now** |
| Query Rewriting | High | Low | **Build Now** |
| Metadata Filtering | High | Low | **Build Now** |
| Confidence Scoring | Medium | Low | Phase 2 |
| Hallucination Detection | Medium | Medium | Phase 2 |
| Self-Reflection / Iterative Refinement | Low | High | **Skip** |
| Agent-Based Pipeline | Low | Very High | **Skip** |
| Fine-Tuning | Low | Very High | **Skip** |

### Details

**Hybrid Search (BM25 + Dense):** Combine keyword and semantic search. Merge with Reciprocal Rank Fusion. Catches exact terms (policy numbers, product codes) that dense vectors miss. +20–30% retrieval quality improvement.

**Cross-Encoder Reranking:** `ms-marco-MiniLM-L-6-v2` scores query-document pairs directly. Run on top-20 retrieved chunks, return top-5. +15–25% relevance improvement.

**Conversation Memory:** Inject last 5 turns before query rewriting. Without this, "what does that clause say?" has no referent. Table stakes for enterprise UX.

**Query Rewriting:** Expand abbreviations, fix typos, add domain context. Especially valuable for enterprise users who type shorthand: "SOP-47" → "Standard Operating Procedure 47 safety protocol".

**Self-Reflection:** 2–3x API cost for marginal quality gain in document Q&A. The retrieval improvements above deliver far more value.

**Agents and Fine-Tuning:** Enormous complexity, unpredictable latency, hard to debug. Document Q&A is a well-defined retrieval task — it doesn't need an agent, and fine-tuning advantages disappear with each new base model version.

> **The highest-leverage combination:** Hybrid search + cross-encoder reranking + conversation memory. These three improvements together will make the answer quality unrecognizable compared to v1. Build these before any exotic AI technique.

---

## 9. Scalability

### Today — Single VPS, Docker Compose

| Layer | Setup |
|---|---|
| Traffic | 1 FastAPI instance · Nginx → FastAPI:8000 · Next.js on Vercel |
| Processing | 2–4 Celery workers · Redis for queue · Ingestion & query separated |
| Data | Qdrant (single node, disk persistence) · PostgreSQL (Docker or Supabase free tier) · MinIO or Cloudflare R2 ($0.015/GB) |

### Growth — 10+ Companies, 1,000+ Employees

| Layer | Setup |
|---|---|
| Traffic | 2–3 FastAPI instances · Nginx load balancer · Redis for API response caching |
| Processing | Separate ingestion worker fleet · Priority queues: fast (query) vs slow (ingestion) |
| Data | Qdrant with snapshots enabled · PostgreSQL with PgBouncer connection pooling · Read replica for analytics |

### Scale — 100 Companies, Millions of Chunks

| Layer | Setup |
|---|---|
| Traffic | Kubernetes (k3s is sufficient) · Horizontal pod autoscaling · Rate limiting per tenant |
| Data | Qdrant cluster (3 nodes) · PostgreSQL + read replicas · Redis Cluster · AWS S3 for file storage |

> **Key insight:** The ingestion pipeline (OCR + chunking + embedding) is the most CPU-intensive part. Isolating it into separate Celery workers from day one is the most important architectural decision you can make. This single separation enables every scaling step above without structural rewrites.

---

## 10. Deployment

### Service Stack

**Local / Staging (Docker Compose)**
- Orchestration: Docker Compose
- Reverse Proxy: Nginx
- HTTPS: Certbot + Let's Encrypt
- PostgreSQL: Docker container
- Qdrant: Docker container
- MinIO: Docker container
- Redis: Docker container

**Production (Cloud)**
- Frontend: Vercel
- Backend + Workers: Railway or Hetzner VPS
- PostgreSQL: Supabase / Neon
- Qdrant: Qdrant Cloud
- File Storage: Cloudflare R2 / AWS S3
- Secrets: Railway env vars / Vault

**CI/CD**
- Pipeline: GitHub Actions
- Stages: Lint → Test → Build → Deploy
- Docker Registry: GitHub Container Registry
- Deploy trigger: Push to main

**Observability**
- Error tracking: Sentry
- Uptime monitoring: Uptime Kuma
- Logs: Structured JSON → Loki
- Metrics: Prometheus + Grafana

> **Cost perspective:** A Hetzner CX21 VPS (2 vCPU, 4GB RAM) costs €4.51/month and runs this entire stack comfortably for a demo or early production. Cloudflare R2 has no egress fees. Supabase free tier handles the PostgreSQL load easily. You can run a production-quality system for under $20/month before you have paying customers.

---

## 11. Enterprise Features

### Tier 1 — High business value, achievable now

| Feature | Description |
|---|---|
| **OCR Support** | Most company documents are scanned — signed contracts, printed manuals, old safety guides. Use Tesseract (free, local) or AWS Textract (cloud, higher accuracy). Without this, the system is useless for 40–60% of real enterprise documents. |
| **Table Extraction** | Financial reports, SOPs, and ISO documents are full of tables that become unreadable after standard PDF text extraction. Use `pdfplumber` or `Camelot` to extract tables as structured data before chunking. |
| **Document Versioning** | Upload v2 of a policy. The system keeps v1 accessible, marks it as superseded, and routes new queries to v2. Companies update policies frequently — versioning is a real requirement. |
| **Slack Bot** | Employees live in Slack. A `/ask` slash command that queries the knowledge base without leaving Slack is the feature that drives adoption faster than any UI improvement. Slack's Bolt SDK makes this straightforward in Python. |
| **Audit Trail** | Log every query: who asked, what they asked, which documents were cited, what the answer was. Table stakes for enterprise buyers (compliance, legal). |

### Tier 2 — High value, higher effort

| Feature | Description |
|---|---|
| **Google Drive Connector** | Auto-ingest documents from a company's Google Drive folder. Monitors for changes and re-ingests updated files. Removes the manual upload step entirely. |
| **SharePoint Connector** | Large enterprises that use Office 365 store everything in SharePoint. Connecting via Microsoft Graph API means zero friction for the IT team. |
| **User Feedback Loop** | Thumbs up / down on answers stored in PostgreSQL, linked to the query and retrieved documents. Use to identify poorly-performing queries and improve retrieval. |
| **Document Expiry Reminders** | Flag documents that haven't been reviewed in 12 months. ISO certifications, safety manuals, and HR policies have review cycles. |

### Tier 3 — Future enterprise

| Feature | Description |
|---|---|
| **SSO / SAML** | Any company with 500+ employees will require single sign-on (Okta, Azure AD, Google Workspace). Hard prerequisite for enterprise sales. |
| **Audio Transcription** | Ingest meeting recordings and training videos via Whisper. "What was decided in the Q3 all-hands about the new expense policy?" |
| **Microsoft Teams Bot** | Same value as the Slack bot but for Microsoft shops. The two integrations together cover nearly every enterprise customer. |

---

## 12. Prioritization Roadmap

Don't start Phase 2 until Phase 1 is deployed and working.

### Phase I — Must Build (6–8 weeks)

*Foundation: everything required to be a real product rather than a prototype.*

- [ ] FastAPI backend replacing Streamlit backend logic
- [ ] Next.js + shadcn/ui frontend with professional chat UI
- [ ] PostgreSQL for metadata, users, organizations
- [ ] Qdrant replacing ChromaDB — persistent, shareable
- [ ] MinIO / S3 for permanent file storage
- [ ] JWT auth (single tenant, roles Admin / Employee)
- [ ] Celery + Redis for async document ingestion
- [ ] Hybrid search: BM25 + dense with RRF merge
- [ ] Cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`)
- [ ] Conversation memory — last 5 turns
- [ ] Streaming responses via SSE
- [ ] Docker Compose for local + VPS deployment

### Phase II — High Value (4–6 weeks)

*Enterprise-ready: multi-tenancy, RBAC, admin tooling, OCR.*

- [ ] Multi-tenancy: row-level security + Qdrant collection isolation
- [ ] Full RBAC (all 5 roles + permission enforcement)
- [ ] Admin panel: user management, collections
- [ ] Analytics dashboard: query volume, popular docs
- [ ] OCR for scanned PDFs (Tesseract)
- [ ] Query rewriting
- [ ] Semantic chunking replacing fixed-char splitting
- [ ] Audit trail (query log viewer)
- [ ] Confidence scoring in UI
- [ ] GitHub Actions CI/CD pipeline

### Phase III — Portfolio Polish (4–6 weeks)

*Differentiators: the features that make enterprise buyers recognize a real product.*

- [ ] Slack bot integration (`/ask` command)
- [ ] Table extraction from PDFs
- [ ] Document versioning
- [ ] Feedback loop (thumbs up/down → analytics)
- [ ] Hallucination detection with warning banner
- [ ] Google Drive connector (auto-ingest)
- [ ] Document expiry reminders
- [ ] Full-text search across past conversations

### Phase IV — Future Enterprise (ongoing)

*When you have customers asking for it.*

- [ ] SSO / SAML (Okta, Azure AD)
- [ ] Microsoft Teams bot
- [ ] SharePoint connector
- [ ] Audio transcription via Whisper
- [ ] Kubernetes deployment (k3s)
- [ ] Multi-region data residency
- [ ] Custom embedding model fine-tuning
- [ ] SLA monitoring and uptime guarantees

---

> **The portfolio inflection point** is the end of Phase 2 — multi-tenancy working, RBAC enforced, OCR ingesting scanned PDFs, analytics showing real usage data, deployed on a real URL. At that point this is no longer a "RAG demo" — it is a product. Phase 3 (Slack bot, versioning, Google Drive) turns it into a product that enterprise buyers recognize immediately. That is your target before sending any job applications.
