# Technical Design — SourcebookLM

Status: draft for build · Date: 2026-10-08
Links: [PRD](prd.md) · [tasks](tasks.md) · [CLAUDE.md](../CLAUDE.md)

This document is the "how": architecture, data model, API contracts, ingestion and retrieval design, key decisions, risks. It is updated in the same slice as any behavior change (CLAUDE.md §9).

## 1. Overview

SourcebookLM is a multi-notebook RAG app. Each notebook owns a set of ingested sources; questions are answered **only** from that notebook's indexed chunks, with citations that deep-link into the original material.

Three deployable pieces: a Next.js web app, a FastAPI API (which also runs an in-process ingestion worker), and Postgres + pgvector. Two external model providers (OpenAI, DeepSeek) plus outbound ingestion calls (websites, YouTube transcripts).

## 2. Architecture

### 2.1 Components

```
web (Next.js, Vercel) ──REST + SSE──▶ api (FastAPI + worker, Render) ──SQL──▶ Postgres + pgvector (Neon)
                                             │
                                             ├──▶ OpenAI API          (embeddings + chat)
                                             ├──▶ DeepSeek API        (chat)
                                             ├──▶ websites            (ingest-time fetch)
                                             └──▶ YouTube transcript  (ingest-time fetch)
```

- **api** is a single FastAPI process: routers (HTTP), services (logic), and a lifespan-managed worker loop (ingestion). One process keeps deployment simple; multiple workers are already safe by design (SKIP LOCKED) if scaled later.
- **No Redis, no Celery, no external search service** — Postgres carries jobs, data, and vectors. This is deliberate (see §8, decision 3).

### 2.2 Module map and rules

```
api/app/
├── main.py            # app factory, lifespan: db init, vector store ensure, worker start
├── config.py          # pydantic-settings (env)
├── db.py              # async engine + session factory
├── models.py          # SQLAlchemy ORM
├── schemas.py         # pydantic request/response models
├── routers/           # notebooks.py, sources.py, chat.py  (HTTP shape only)
├── services/
│   ├── ingestion/     # extractors/ + chunker.py + indexer.py + graph.py + worker.py
│   └── rag/           # retriever.py + prompt.py + generator.py
└── evals/             # retrieval eval harness (P4)
```

Rules: routers never query the ORM with business meaning and never call models; services are reusable by both routers and worker; worker and API share the same services.

### 2.3 Request flows

**Ingestion (async):** client `POST …/sources` → row created `queued` (file bytes stored if upload) → worker claims → LangGraph runs `extract → chunk → embed+index`, updating `stage` → row `ready` (or `failed` + error). Client polls `GET …/sources` every 2 s while anything is active.

**Query (sync stream):** client `POST …/query` → embed question → notebook-filtered vector search (12 candidates) → MMR → top 6 → build numbered context → stream LLM tokens as SSE, citations payload sent before tokens → persist assistant message + citations snapshot → `done` event.

## 3. Data model

Postgres 17 (Neon prod, docker pg17 locally), extension `vector`. All IDs `uuid` with `default gen_random_uuid()`; all timestamps `timestamptz` (`now()` defaults). Status/stage values are `text` + `CHECK` (easy to evolve; no PG enums).

### 3.1 Relational tables

```
notebooks
  id, name (1..100 chars), created_at, updated_at

sources
  id, notebook_id ──▶ notebooks (ON DELETE CASCADE)
  kind            text CHECK in ('pdf','text','url','youtube','vtt')
  title           text NOT NULL
  status          text default 'queued'  CHECK in ('queued','processing','ready','failed')
  stage           text NULL CHECK in ('extracting','chunking','embedding','indexing')
  error           text NULL
  chunk_count     int NULL
  char_count      int NULL
  config          jsonb NOT NULL default '{}'   -- url, video_id, filename, size_bytes, etc.
  created_at, updated_at
  INDEX (notebook_id, created_at DESC), INDEX (status)

source_files                       -- uploaded originals (pdf, vtt)
  source_id ──▶ sources (ON DELETE CASCADE) PK
  filename, content_type, size_bytes, bytes bytea

source_contents                    -- extracted snapshot for viewers + re-index
  source_id ──▶ sources (ON DELETE CASCADE) PK
  text      text NULL              -- plain text (text, url sources)
  pages     jsonb NULL             -- [{page:int, text:str}] (pdf)
  segments  jsonb NULL             -- [{text:str, start:float, end:float}] (youtube, vtt)
  fetched_at

conversations
  id, notebook_id ──▶ notebooks (ON DELETE CASCADE), created_at

messages
  id, conversation_id ──▶ conversations (ON DELETE CASCADE)
  role text CHECK in ('user','assistant')
  content text NOT NULL
  citations jsonb NULL             -- snapshot on assistant messages: [{n, source_id, title, kind, page, start_seconds, url, snippet}]
  model text NULL                  -- e.g. 'deepseek:deepseek-chat'
  created_at
  INDEX (conversation_id, created_at)
```

### 3.2 Vector store

- Managed by `langchain-postgres` **PGVector** (tables `langchain_pg_collection` / `langchain_pg_embedding`); a single collection named **`chunks`**.
- Embedding: **1536-d** (`text-embedding-3-small`), cosine distance.
- Metadata per chunk (jsonb): `notebook_id`, `source_id`, `source_type`, `chunk_index`, `title`, plus type-specific: `page` (pdf), `start_seconds`/`end_seconds` (youtube, vtt), `url` (url), `char_start`/`char_end` where known.
- **Every similarity search filters by `notebook_id`** — isolation is a retrieval-level invariant, enforced in `retriever.py` (tested).
- HNSW index (`vector_cosine_ops`) created idempotently at startup by `ensure_vector_store()` (PGVector owns its DDL; a startup helper avoids fighting Alembic over it).

### 3.3 Cascade rules

Delete notebook → sources → files/contents → messages; and vector deletion by `notebook_id` metadata filter. Delete source → vectors by `source_id` filter + rows. Re-index = delete vectors by `source_id`, reset status to `queued`, rerun (idempotent).

## 4. API design

Conventions: prefix `/api/v1`; plural nouns; JSON `snake_case` everywhere (no case transforms between Python and TS); FastAPI default error shape `{detail}`; `201` create, `204` delete; all list endpoints are notebook-scoped except `/health`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | liveness (+ db reachable) |
| GET | `/api/v1/notebooks` | list notebooks |
| POST | `/api/v1/notebooks` | create `{name}` |
| GET/PATCH/DELETE | `/api/v1/notebooks/{id}` | detail / rename `{name}` / delete (cascade) |
| GET | `/api/v1/notebooks/{id}/sources` | sources with status/stage/chunk_count |
| POST | `/api/v1/notebooks/{id}/sources` | add source — `multipart/form-data` |
| GET | `/api/v1/sources/{id}` | source detail |
| GET | `/api/v1/sources/{id}/content` | viewer payload (`text` / `pages` / `segments`) |
| GET | `/api/v1/sources/{id}/file` | stream original upload (pdf/vtt) |
| POST | `/api/v1/sources/{id}/reindex` | re-run ingestion |
| DELETE | `/api/v1/sources/{id}` | delete source + vectors |
| GET | `/api/v1/notebooks/{id}/messages` | conversation history (creates default conversation lazily) |
| POST | `/api/v1/notebooks/{id}/query` | ask; **SSE response** |

**Add-source multipart fields:** `kind` (`pdf`|`text`|`url`|`youtube`|`vtt`), `title?`, `text?` (kind=text), `url?` (kind=url), `youtube_url?` (kind=youtube), `file?` (kind=pdf|vtt). Server validates against `kind` and `MAX_UPLOAD_MB`.

**Query SSE contract:**

```
event: meta
data: {"message_id":"…","conversation_id":"…"}

event: citations                         # sent before tokens so the UI can render chips early
data: {"sources":[{"n":1,"source_id":"…","title":"Lecture 3","kind":"youtube",
                   "start_seconds":412.5,"page":null,"url":null,"snippet":"…"}]}

event: token
data: {"t":"Backpropagation "}

event: done
data: {"message_id":"…","model":"deepseek:deepseek-chat","usage":{"prompt_tokens":0,"completion_tokens":0}}

event: error
data: {"detail":"…"}
```

## 5. Ingestion pipeline

### 5.1 Status machine

`queued → processing(stage) → ready | failed`

- `stage`: `extracting → chunking → embedding → indexing` (UI granularity).
- Worker startup: `UPDATE sources SET status='queued', stage=NULL WHERE status='processing'` (crash recovery).
- Worker loop: claim one row `… WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1` → process → sleep 1 s when idle.
- Failure at any point: `status='failed'`, human-readable `error`, vectors from partial runs cleaned by `source_id`.

### 5.2 LangGraph

The pipeline is a `StateGraph` over `IngestState {source_id, notebook_id, kind, config}` with nodes `extract → chunk → embed_and_index`, plus a conditional `mark_failed` terminator on error. LangGraph is used **here** (deterministic multi-step job with per-node error handling and stage writes); the answer path stays plain explicit code until P4 (no agent loops needed to answer questions). This is intentional scope, not an omission.

### 5.3 Extractors

| Kind | Library | Produces | Metadata used later |
|---|---|---|---|
| `text` | — | `source_contents.text` | — |
| `pdf` | `pypdf` via LangChain `PyPDFLoader` | per-page documents + `pages` snapshot | `page` |
| `url` | LangChain `WebBaseLoader` | text snapshot (+ title if found) | `url` |
| `youtube` | `youtube-transcript-api` + oEmbed title | `segments [{text,start,end}]` | `start_seconds`, `end_seconds`, `url`, `video_id` |
| `vtt` | custom parser (WEBVTT cues) | `segments [{text,start,end}]` | `start_seconds`, `end_seconds` |

Extractor settings and failure texts are per-kind; all failures land in `sources.error`.

### 5.4 Chunking strategy

- Plain text / URL / PDF pages: `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)` (chars).
- Transcripts (YouTube, VTT): accumulate cues into chunks until ~1000 chars, with one-cue overlap; `start_seconds` = first cue's start, `end_seconds` = last cue's end. Never splits mid-cue — timestamps stay truthful.
- PDF: page text split per page; `page` preserved on each chunk; pages never merged (keeps citations addressable).
- P4 will measure refinements (params, semantic chunking experiment) against the eval set before changing defaults.

### 5.5 Embedding & indexing

- `OpenAIEmbeddings(model="text-embedding-3-small", dimensions=1536)`; batch ~100 documents; retry with backoff on rate limits.
- Add to PGVector collection `chunks` with metadata (§3.2); set `sources.chunk_count` + `char_count`; stage `indexing` → `ready`.

## 6. Retrieval & answers

### 6.1 Retrieval

1. Embed question (same model as ingestion).
2. Similarity search with `filter={"notebook_id": …}`, k=12.
3. MMR (λ≈0.5) → top 6. P4 may add query rewrite and/or rerank, each measured (§12).
4. Assemble numbered context; cap ~12 000 chars of context, dropping lowest-ranked overflow.

### 6.2 Prompt (citation-constrained)

```
System:
You are a research assistant answering only from the user's notebook sources.
Rules:
- Use ONLY the numbered context below. Never use outside knowledge.
- Cite every claim with its source number in brackets, e.g. [1]. Use multiple [n] where sources agree.
- If the context does not contain the answer, say you couldn't find it in this notebook's sources
  and suggest what to add. Do not guess.
- Format with Markdown. Be concise unless asked for detail.

Context:
[1] "{title}" — page {page}
{chunk text}

[2] "{title}" — {start_seconds}s
{chunk text}

Question: {question}
```

### 6.3 Citation protocol

- The prompt numbers context blocks `[1…n]`; the model must cite `[n]`.
- The API builds the `citations` payload from the exact chunks used (snippet = first ~200 chars), sends it as the second SSE event, and persists it on the assistant message — so clicking a chip later resolves against the answer-time snapshot, never a fresh query.

### 6.4 Models & streaming

- Provider switch: `CHAT_PROVIDER=openai|deepseek`; `OPENAI_CHAT_MODEL` (current small model, confirmed at P3.2), `DEEPSEEK_CHAT_MODEL=deepseek-chat`; temperature 0.2.
- SSE via `sse-starlette`; token events as the LangChain/OpenAI stream yields; client disconnects cancel the upstream request.
- Conversation persistence: one conversation per notebook (lazily created); user message + assistant message (+citations, model) stored.

## 7. Frontend design

- Routes: `/` notebooks overview; `/notebooks/[id]` workspace — left sources panel, center chat, right viewer panel that opens when a citation is clicked (per official mockups, `../assignments.md` → "Mock up").
- Key components: `NotebookCard`, `CreateNotebookDialog`, `SourceList`, `SourceStatusChip` (dot + short label: yellow = indexing, green = ready, red = failed), `AddSourceDialog` (five source tiles: PDF · YouTube link · Web link · Text · VTT — per mockup), `SourceViewer` (per-kind: `PdfViewer` via `react-pdf` / `YoutubePlayer` iframe `?start=` / `TranscriptViewer` cue-highlight / `TextViewer` substring-highlight), `ChatPanel` (`MessageList`, `CitationChip`, `Composer`).
- State: local React state + two custom hooks — `useSources` (2 s polling while any source is active, stops when settled) and `useChatStream` (fetch-reader SSE parsing). No global store; no extra data library.
- API client: `src/lib/api.ts` + `api-types.ts` generated by `openapi-typescript` from the running API — types can't drift.

## 8. Key decisions

| # | Decision | Why | Alternatives rejected |
|---|---|---|---|
| 1 | LangChain 1.x + LangGraph | User-selected; biggest ecosystem/docs; explicit RAG building blocks (loaders, splitters, PGVector, providers) — legible in evaluation | LlamaIndex (0.x core), Haystack, PydanticAI + hand-rolled RAG |
| 2 | pgvector on Postgres (single DB) | One datastore for jobs + data + vectors; Neon already available; isolation via metadata filter | Qdrant, Pinecone (extra service/creds for no demo benefit) |
| 3 | Postgres-backed job queue | No Redis/Celery; `FOR UPDATE SKIP LOCKED` is exactly enough at this scale; crash recovery trivial | Celery+Redis, arq, in-request BackgroundTasks (no durability) |
| 4 | One vector collection + `notebook_id` filter | Central enforcement point; simpler deletes/ops; per-notebook collections add naming/management overhead | Collection per notebook |
| 5 | PDF/VTT bytes in Postgres (`bytea`) | No object-storage credentials; ≤20 MB files; Neon storage is fine for demo | S3/R2/Cloudflare, local disk (dies on Render) |
| 6 | SSE, not WebSocket | One-way stream; simpler protocol; proxy-friendly | WebSocket, polling |
| 7 | `snake_case` JSON + OpenAPI-generated TS types | Zero mapping layer; FE types generated from the source of truth | camelCase transforms, hand-written types |
| 8 | No auth; one conversation per notebook | Scope control — rubric grades RAG, not identity | Auth providers, multi-tenant model |
| 9 | LangGraph for ingestion only | Deterministic pipeline with retries/stage-writes; answer path stays explicit readable code | Agentic query loops now (deferred to P4 if measurable) |
| 10 | uv + ruff + mypy / bun | Modern, fast toolchain; bun matches the sibling project | pip/poetry; npm/pnpm |

## 9. Security & privacy

- Single-user demo by design (no auth): no personal data stored; keep the app non-sensitive.
- Secrets only in env (`.env` local, provider dashboards in prod); never logged, never committed.
- CORS allowlist (`WEB_ORIGIN`), upload size/MIME caps.
- **Prompt-injection awareness**: retrieved text is untrusted data — the system prompt constrains the model to cite-only behavior; no tools/actions are exposed to the model, so injections can at worst produce a bad answer in the user's own notebook.
- **URL fetch hardening** (P5.2): http/https schemes only; block private/loopback IPs (SSRF guard).

## 10. Deployment

| Tier | Platform | Notes |
|---|---|---|
| web | Vercel | `NEXT_PUBLIC_API_URL` → Render URL |
| api | Render web service | build `uv sync`; start `uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| db | Neon | pooled connection string for runtime; direct string for migrations if pooling interferes |

CORS: `WEB_ORIGIN` = deployed web origin. Cold starts on free tiers are acceptable for a demo; note them in the README. Migrations run on deploy (idempotent).

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| YouTube transcript fetch blocked/rate-limited | Fetch at ingest time only once, store segments snapshot; readable failure + retry; test locally before deploy |
| JS-heavy pages extract poorly via `WebBaseLoader` | Document; trafilatura fallback (⭐ P8.3); failure states are visible |
| OpenAI cost creep | `text-embedding-3-small`, cheap chat default, batch embeddings, file/context caps |
| Neon free-tier storage/compute | Demo-scale data; caps; upgrade path documented |
| Render free cold start | Expect a slow first request; optional keep-warm pinger; noted in README |
| HNSW index build time as data grows | Built once at startup; demo scale is small; acceptable |
| pgvector + Alembic ownership overlap | PGVector owns its tables; we add the HNSW index in an idempotent startup helper, not migrations |

## 12. Testing & evaluation

- **Unit**: VTT parser, chunker (incl. transcript grouping), prompt/citation builders.
- **Integration** (docker Postgres): worker status transitions + crash recovery, notebooks CRUD + cascade, ingestion per kind with fixtures, retriever isolation, refusal path.
- **Retrieval evaluation** (P4.1): 12–15 handcrafted question → expected-source pairs across types; `uv run python -m app.evals.retrieval` prints hit@k; baseline vs improved configs recorded in the progress log / an ADR. A retrieval change ships only with numbers.
