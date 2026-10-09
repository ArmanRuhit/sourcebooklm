# SourcebookLM — Working Notes (CLAUDE.md)

**Read me first.** Single source of truth for `sourcebooklm`: mission, rubric analysis, architecture, conventions, pairing workflow, roadmap, and the live progress log. [`AGENTS.md`](AGENTS.md) defers here.

Cohort rules live in [`../../CLAUDE.md`](../../CLAUDE.md) (Codecrafters format: brief → attempt → hints → verify). **Exception — owner directive (2026-10-08):** this project runs in **pair-typing mode** (§7 — the owner wants the full per-slice code in chat to type by hand). The Codecrafters default does not apply here. **Amendment (2026-10-10):** per-slice quizzes are deferred to post-project review — see §7.1 step 5 ([`docs/quiz-bank.md`](docs/quiz-bank.md)).

Last updated: 2026-10-10 · Status: **P0.2 complete — FastAPI app + health endpoint green; P0.3 (local infra) up next**

## 1. Mission & success criteria

Build **SourcebookLM** — an AI research assistant inspired by Gemini Notebook: multi-notebook workspaces where a user adds sources (PDF, plain text, website URL, YouTube video, VTT transcript) and asks questions answered **only** from those sources, with citations that deep-link back into the original material.

Goals:

1. Ship a working end-to-end RAG app: add sources → index → ask → grounded, cited answers.
2. Support all five source types with a visible, recoverable ingestion lifecycle (queued / processing / ready / failed).
3. Never answer without provenance: every answer cites inspectable moments in the original sources.
4. Keep notebooks isolated in data *and* retrieval (every query filtered by `notebook_id`).
5. Produce a codebase that holds up on architecture, tests, and documentation — not just a demo.

Success checklist:

- [ ] All 10 rubric items covered (see §2) with demo evidence
- [ ] Live deployment + public repo + README + demo video (submission items)
- [ ] Local setup reproducible from the README on a clean machine
- [ ] `uv run pytest` green, `ruff` clean, `/docs` (OpenAPI) accurate

Non-negotiables:

- Every answer grounded in retrieved context; empty context → explicit refusal.
- Notebook isolation never broken — no query without the `notebook_id` filter.
- Ingestion survives API restarts (persistent statuses + worker recovery).
- No secrets in git; `.env.example` always current.

## 2. Rubric analysis (assignment → where we answer)

The assignment's *Evaluation Parameters* are the grading rubric. The header says "Max Marks: 100" but the item marks sum to **130** — treat every item as full-weight and answer all of them.

| Rubric item (marks) | What the evaluator probes | Where we answer |
|---|---|---|
| 1. Notebook Management (10) | multiple notebooks, create/rename/delete, isolation, clean UX | Phase 1: `notebooks` model + CRUD API + web list/dialog; isolation enforced in §9 |
| 2. Source Ingestion (20) | all 5 source types, upload flow, indexing pipeline, status indicators, removal | Phase 2: per-type extractors, ingestion graph, Postgres-backed worker, status machine, remove/re-index |
| 3. RAG Pipeline (20) | chunking strategy, embedding generation, vector search, metadata, retrieval quality | Phase 2 chunker + pgvector; Phase 3 retriever; Phase 4 eval harness + MMR/rerank |
| 4. AI Responses (15) | grounded, streaming, prompt construction, minimal hallucination, formatting | Phase 3: SSE streaming, citation-constrained prompt, refuse-if-empty, Markdown answers |
| 5. Citations & Source Attribution (15) | every answer cited, inspect originals, metadata preserved, clear citation UX | Phase 3/4: `[n]` protocol, per-message citation snapshots, per-type viewer deep-links |
| 6. Architecture & Code Quality (10) | folder structure, separation, reusable components, error handling, maintainable | monorepo, routers→services→db layering, typed schemas, tests per slice, decision records |
| 7. UI/UX (10) | responsive, loading states, empty states, smooth interactions | Phase 5 polish + states built in from Phase 1–3 (skeletons, toasts, drawers) |
| 8. README & Documentation (10) | setup, architecture, retrieval flow, env vars, easy to run | `docs/` live now; README in P6.2; env table kept current |
| 9. Demo Video (10) | features, end-to-end, technical decisions, followable | P7.1 — script-first video built on §3.3 flows |
| 10. Engineering Thoughtfulness (10) | system design, practical choices, retrieval quality, production thinking, RAG understanding | Postgres job queue (no Redis), crash recovery, eval harness, ADRs, cost caps |

**Strategy line:** 40 of 130 marks sit in ingestion + RAG pipeline; 30 more in answers + citations. Depth goes there first; UI, docs, and video carry the rest.

## 3. Product scope

### 3.1 MVP feature map

| Feature | Rubric | Phase |
|---|---|---|
| Notebook CRUD + isolation | 1, 6 | P1 |
| Add source: plain text | 2 | P2 |
| Add source: PDF (upload, file serving, page jumps) | 2, 5 | P2 |
| Add source: website URL | 2 | P2 |
| Add source: YouTube video (timestamped transcript) | 2, 5 | P2 |
| Add source: VTT transcript | 2 | P2 |
| Ingestion lifecycle: statuses, progress, remove, re-index | 2 | P2 |
| Retrieval: pgvector search, notebook filter, metadata | 3 | P2/P3 |
| Grounded streaming answers | 4 | P3 |
| Citation protocol + viewer deep-links | 5 | P3/P4 |
| Retrieval quality: eval set, MMR, query rewrite / rerank | 3, 10 | P4 |
| UX polish (states, responsive, a11y) | 7 | P5 |
| Deploy + README + demo video | R8, R9, submission | P6/P7 |
| ⭐ YouTube playlist → learning roadmap | bonus | P8 |
| ⭐ Podcast-style voice-over | bonus | P8 |

### 3.2 Non-goals (and how to answer)

- **Auth / multi-user** — single-user demo workspace; the rubric does not grade auth. Answer template: *"Out of scope by design — the assignment evaluates RAG depth; the data model stays user-free to keep focus."*
- **Sharing / real-time collaboration, native mobile apps, payments, fine-tuning, analytics dashboards** — same reasoning; note them here, don't build them.

### 3.3 Killer demo flows (record these for the video)

1. **Cross-source answer** — a notebook contains a PDF + an article + a lecture video; ask one question answered by two of them; click each citation → lands on the exact page / timestamp / highlighted passage.
2. **Trust boundary** — delete one source, re-ask the same question → the answer changes (drops that citation, or says it can't find it).
3. **Isolation** — the same topic in two notebooks → each answers only from its own sources.

## 4. Architecture at a glance

```
┌──────────────────────┐       REST /api/v1        ┌────────────────────────────────┐
│ web — Next.js 16     │ ────────────────────────▶ │ api — FastAPI (Python 3.13)    │
│ Vercel               │ ◀────── SSE stream ────── │ Render                         │
└──────────────────────┘                           │   ├─ routers/   (HTTP only)    │
                                                   │   ├─ services/  (logic)        │
                                                   │   └─ worker     (ingestion)    │
                                                   └───────┬───────────────┬────────┘
                                                           │ SQL (async)   │ outbound (ingest)
                                                           ▼               ▼
                                                 Postgres + pgvector     OpenAI API (embed + chat)
                                                 Neon (prod) / docker    DeepSeek API (chat)
                                                                         website fetch · YouTube transcripts
```

Module rules:

- `routers/` = HTTP shape only; no ORM queries with business meaning, never call LLMs directly.
- `services/` = all logic (ingestion, retrieval, answer generation); reusable from API and worker.
- `worker` = background loop claiming ingestion jobs from Postgres; uses the same services.
- Shared Pydantic schemas in `schemas.py`; ORM models only in `models.py`.

Key mechanisms (details in [`docs/technical-design.md`](docs/technical-design.md)):

- **Postgres job queue** — worker claims queued sources with `SELECT … FOR UPDATE SKIP LOCKED`; no Redis/Celery.
- **Status machine** — `queued → processing(stage) → ready | failed` stored on `sources`; survives restarts.
- **Metadata-filtered vector store** — one pgvector collection `chunks`; every search filters by `notebook_id`.
- **Citation snapshots** — each assistant message stores the exact `[n] → chunk` mapping used at answer time.
- **SSE** — token streaming plus a citations payload; consumed with `fetch` streams in the web app.
- **OpenAPI-generated TS types** — `openapi-typescript` from FastAPI's `/openapi.json`.

## 5. Tech stack (pinned)

Versions verified 2026-10-08 (PyPI/npm). Bump only deliberately, in a slice that notes why.

| Layer | Choice | Notes |
|---|---|---|
| Repo | monorepo: `web/` + `api/` + `infra/` | independent projects, not a workspace tool |
| Frontend | Next.js **16.4.0** (App Router, TS strict, Tailwind 4, shadcn/ui), React 19 | package manager: **bun** |
| Backend | Python **3.13** · FastAPI **0.142** · uvicorn · pydantic **2.13** · pydantic-settings | package manager: **uv** |
| AI framework | LangChain **1.4** (core 1.6, + `langchain-openai`, `langchain-deepseek`, `langchain-community`, `langchain-text-splitters`) + LangGraph **1.2** | LangGraph runs the ingestion pipeline |
| Vector store | Postgres + pgvector via `langchain-postgres` **PGVector** (0.0.19, current) | single collection `chunks`, metadata filter |
| Database | Neon Postgres (prod) / pgvector docker (dev) · SQLAlchemy **2.1** async + psycopg **3.3** + Alembic **1.20** | migrations per slice |
| Models | embeddings: OpenAI `text-embedding-3-small` (1536-d) · chat: OpenAI (env-configured) + DeepSeek `deepseek-chat` (provider switch via env) | keys in `.env` only |
| Streaming | SSE via `sse-starlette` → `fetch` stream in Next | events: `meta`, `citations`, `token`, `done`, `error` |
| Deploy | Vercel (web) · Render (api) · Neon (db) | default targets, revisable at P6.1 |

## 6. Target repo layout

```
sourcebooklm/
├── CLAUDE.md                  # this file — SSOT + workflow + progress
├── AGENTS.md                  # agent entry (defers here)
├── README.md                  # submission-facing (P6.2)
├── docs/
│   ├── prd.md                 # what & why
│   ├── technical-design.md    # how — architecture, data model, API, pipelines
│   ├── tasks.md               # every slice with acceptance criteria
│   └── adr/                   # decision records (from P1 onward)
├── api/                       # FastAPI (uv project)
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/versions/
│   ├── .env.example
│   ├── app/
│   │   ├── main.py            # app factory + lifespan (worker startup)
│   │   ├── config.py          # pydantic-settings
│   │   ├── db.py              # async engine/session
│   │   ├── models.py          # SQLAlchemy ORM
│   │   ├── schemas.py         # pydantic API models
│   │   ├── routers/           # notebooks.py, sources.py, chat.py
│   │   ├── services/
│   │   │   ├── ingestion/     # extractors, chunker, indexer, graph, worker
│   │   │   └── rag/           # retriever, prompt, generator
│   │   └── evals/             # retrieval eval harness (P4)
│   └── tests/
├── web/                       # Next.js (bun)
│   └── src/ (app/, components/, lib/)
└── infra/
    └── docker-compose.yml     # pgvector local dev
```

## 7. Working agreement (pair-typing)

### 7.1 The loop (every slice)

For each slice the agent posts, in chat, one step at a time:

1. **Goal** — 2–3 lines: what the slice does and which rubric item it serves.
2. **Concepts** — 3–6 bullets + official docs links for anything new (LangChain / LangGraph / FastAPI / pgvector / Next).
3. **Code** — **ONE FILE PER MESSAGE**, complete file contents (not fragments), then **stop**. The owner types it, then replies `next` for the following file.
4. **Verify** — exact commands + expected output, once all files of the slice are typed.
5. **Quiz (deferred — owner directive 2026-10-10):** the agent still writes the 3 questions (one fundamental, one tradeoff, one failure-mode) but **banks** them in [`docs/quiz-bank.md`](docs/quiz-bank.md); we answer them in **post-project review sessions** (or on demand — say "quiz me"). Time-crunch mode: slices don't wait on quiz answers.

Rules:

- The agent **never creates or edits files under `api/`, `web/`, or `infra/`** — all code lives in chat. It **may** update `docs/` and §11 of this file.
- Modifications arrive as unified diffs or minimal before/after snippets — never full re-posts of already-typed files.
- The owner may pause and ask `explain …` at any point; the agent explains before continuing.
- A slice is done only when: **typed + verification green + committed** (quizzes banked for post-project review — amendment 2026-10-10).
- After each slice: agent updates §11 + any affected docs, then proposes the next slice.
- Ambiguity → **ask**, don't guess.

### 7.2 Output style — `i-have-adhd` (ON for this project)

<!-- BEGIN:i-have-adhd -->
The owner asked for ADHD-friendly output. Apply to every reply in this repo:

- **Lead with the single next action** (imperative, one line).
- Number the steps; one idea per line; no walls of text.
- **Restate state every turn**: where we are in the roadmap, what just happened, what's next.
- **End with ONE action that takes under 2 minutes** to do or decide. If it needs more, cut it down.
- Cap lists at 5 items; if longer, split into "now" vs "later".
- Errors: state what failed and the fix. Matter-of-fact. No blame, no drama, no apologies.
- Make wins visible: name finished slices and green verifications briefly.
- Off switches: "stop adhd mode" / "normal mode". Repo conventions outrank this style.
<!-- END:i-have-adhd -->

## 8. Roadmap

Pace context: assignment due **1 Jan 2027** (~12 weeks from 2026-10-08). Target: **P0–P3 by end of November** (demo-safe app), **P4–P7 done by mid-December**, submission-ready with buffer; ⭐ P8 only after P7.

**Demo-safe stop points:** after **P3** (full loop works), after **P4** (rubric depth complete), after **P6** (submittable), after **P7** (done).

### Phase 0 — Foundation (P0)

- [x] P0.1 Repo init: `git init`, `.gitignore`, folder skeleton, README placeholder, first commit
- [x] P0.2 API scaffold: uv project, pinned deps, `/api/v1/health`, ruff + pytest green
- [ ] P0.3 Local infra: docker-compose pgvector, `.env.example`
- [ ] P0.4 Web scaffold: Next 16 + Tailwind + shadcn, page showing API health

*Exit:* `docker compose up -d` + `uv run uvicorn` serves health; `bun dev` shows it; both test/lint suites green.

### Phase 1 — Notebooks & data core (P1)

- [ ] P1.1 Schema + migrations: all tables + pgvector extension
- [ ] P1.2 Notebooks CRUD API + tests
- [ ] P1.3 Notebooks UI (list, create, rename, delete, empty state) + generated API types
- [ ] P1.4 Notebook page shell (sources panel + chat area placeholders)

*Exit:* full notebook CRUD from the browser, persisted in Postgres, typed API client wired.

### Phase 2 — Ingestion pipeline (P2) — *rubric item 2 (20)*

- [ ] P2.1 Source API + worker skeleton (status machine, claim loop, crash recovery)
- [ ] P2.2 Text source end-to-end: chunk → embed → pgvector → `ready`
- [ ] P2.3 PDF: upload, bytea storage, file serving, viewer opens at page
- [ ] P2.4 Website URL extraction
- [ ] P2.5 YouTube transcript extraction (timestamped segments)
- [ ] P2.6 VTT transcript parsing
- [ ] P2.7 Remove / re-index / failure states + status polling UI

*Exit:* all five source types ingest to `ready` with correct metadata; delete removes vectors; failures visible + retryable.

### Phase 3 — RAG chat (P3) — *rubric items 4 (15) and part of 3, 5*

- [ ] P3.1 Retriever module (notebook-filtered similarity search) + tests
- [ ] P3.2 Streaming query endpoint: SSE + citation prompt + citation payload
- [ ] P3.3 Chat UI: streaming render, Markdown, citation chips
- [ ] P3.4 Citation deep-links into the source viewer (all five types, MVP fidelity)
- [ ] P3.5 Conversation history + grounding polish (refusals, errors)

*Exit:* ask → streamed grounded answer → clickable citations; history persists across reloads.

### Phase 4 — Retrieval quality (P4) — *rubric items 3, 10*

- [ ] P4.1 Retrieval eval harness + handcrafted Q/A fixture set (baseline numbers recorded)
- [ ] P4.2 Upgrades: transcript-aware chunking, MMR, query rewrite and/or rerank — measured
- [ ] P4.3 Highlight fidelity: PDF page + snippet, transcript cue highlight, text offset highlight

*Exit:* eval improvement documented; citations land with visible highlighting in at least 3 source types.

### Phase 5 — UX & hardening (P5) — *rubric item 7*

- [ ] P5.1 UX states pass: skeletons, empty states, disabled states, toasts, responsive
- [ ] P5.2 Error/edge hardening: upload validation, duplicates, API error handling
- [ ] P5.3 ⭐ Accessibility quick pass (keyboard nav, focus, labels)

*Exit:* every user-visible flow has loading/empty/error handling; passes a self-run UX checklist.

### Phase 6 — Deploy & README (P6) — *submission items + rubric 8*

- [ ] P6.1 Deploy: Neon (prod db + migrations), Render (api), Vercel (web), CORS
- [ ] P6.2 README + docs final: setup, architecture, retrieval flow, env vars, screenshots

*Exit:* live URL works end-to-end; fresh-clone setup verified from the README.

### Phase 7 — Demo video & submission (P7) — *rubric item 9*

- [ ] P7.1 Demo video: script (built on §3.3) → record → publish
- [ ] P7.2 Submission pass: repo public, §13 checklist complete

*Exit:* all submission items done; app + video + docs mutually consistent.

### Phase 8 — ⭐ Stretch (P8) — only after P7

- [ ] P8.1 ⭐ YouTube playlist → personalized learning roadmap
- [ ] P8.2 ⭐ Podcast-style voice-over (TTS) with audio player
- [ ] P8.3 ⭐ Hybrid search (Postgres FTS + vector) + semantic-chunking experiment

## 9. Conventions

- **Python**: uv manages env/deps; `ruff` formats and lints; `mypy` on `app/`; Pydantic v2 schemas at the API boundary, separate from ORM models; routers never return ORM rows.
- **Async style**: SQLAlchemy 2 async (`select()`), psycopg3 driver (`postgresql+psycopg://`); one session per request via dependency; the worker owns its own sessions.
- **DB**: plural snake_case tables; UUID PKs default `gen_random_uuid()`; `timestamptz` with server defaults; FKs named `{table}_id`; statuses as text + CHECK; Alembic migrations only, never edits to applied ones.
- **Vector store**: single collection `chunks`; metadata keys `notebook_id`, `source_id`, `source_type`, `chunk_index`, `page`, `start_seconds`, `end_seconds`, `url`, `title`; **every search filters by `notebook_id`**; cosine distance; HNSW index.
- **Ingestion**: statuses `queued/processing/ready/failed`; `stage` for UI granularity (`extracting/chunking/embedding/indexing`); failures store `error` text; startup requeues stale `processing` rows.
- **Chunking**: default recursive split, `chunk_size=1000`, `chunk_overlap=150` (chars); transcripts grouped by cues until ~1000 chars, preserving start/end times; per-type params documented in the design doc.
- **Retrieval & prompt**: top-k 6 (from 12 MMR candidates once P4 lands); context blocks numbered `[1…n]`; the model must cite `[n]`; no context → refuse; conversation persistence per §design.
- **Citations**: assistant messages store a `citations` jsonb snapshot `[{n, source_id, chunk metadata, snippet}]`; the UI resolves `[n]` chips → snapshot → viewer.
- **API**: prefix `/api/v1`; plural nouns; JSON `snake_case` everywhere (no case transforms); FastAPI default error shape `{detail}`; 201/204 for create/delete; SSE events `meta → citations → token* → done | error`.
- **Config**: pydantic-settings; every variable in `.env` and `.env.example` (`DATABASE_URL`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `CHAT_PROVIDER`, `OPENAI_CHAT_MODEL`, `DEEPSEEK_CHAT_MODEL`, `EMBEDDING_MODEL`, `WEB_ORIGIN`, `MAX_UPLOAD_MB`); new var = same-slice update to `.env.example`.
- **Logging**: stdlib logging; worker logs `source_id` + stage + duration; request logs via middleware; never log secrets or full source text.
- **Tests**: pytest + pytest-asyncio + httpx; unit tests for parsers/chunkers; integration tests against the docker Postgres; run per slice.
- **Frontend**: TS strict; App Router; client components only where interactive; a single typed API client (`src/lib/api.ts` + generated `api-types.ts`); Tailwind + shadcn/ui only; **2s polling** while any source is active.
- **Commits**: conventional (`feat(api):`, `feat(web):`, `fix:`, `docs:`, `chore:`); one slice ≈ one commit; the agent proposes the message; never commit `.env`.
- **Docs-first**: behavior changes update `docs/technical-design.md` in the same slice; §11 updated after each slice; consequential decisions → `docs/adr/NNNN-*.md`.

## 10. Commands

```bash
# infra (repo root) — available from P0.3
docker compose -f infra/docker-compose.yml up -d      # pgvector on :5432

# api — available from P0.2
cd api
uv sync                                    # install/lock deps
uv run alembic upgrade head                # migrations (from P1.1)
uv run uvicorn app.main:app --reload       # http://localhost:8000/docs
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy app

# web — available from P0.4
cd web
bun install
bun dev                                    # http://localhost:3000
bun run build

# regenerate API types (api running) — from P1.3
bunx openapi-typescript http://localhost:8000/openapi.json -o src/lib/api-types.ts
```

## 11. Progress log

### 2026-10-08 — Planning (Phase 0 kickoff)

- Created `docs/prd.md`, `docs/technical-design.md`, `docs/tasks.md`; this file + `AGENTS.md` are live.
- Decisions locked: FastAPI + LangChain 1.x/LangGraph + pgvector on Neon + OpenAI/DeepSeek; pair-typing mode with `i-have-adhd` on; monorepo `web/`/`api/`/`infra/`.
- Versions verified against PyPI/npm and pinned in §5.
- Project renamed to **SourcebookLM** — folder/slug `sourcebooklm`; `git init` (branch `main`).
- P0.1 (partial): `.gitignore` added; first commit `6b942c8` (8 files); public repo pushed → https://github.com/ArmanRuhit/sourcebooklm. Remaining: README placeholder, folder skeleton.
- No code yet. **Next: finish P0.1 (README + skeleton) → then P0.2 — API scaffold.**

### 2026-10-09 — P0.1 complete (repo init)

- README placeholder added; commit `0a1d41e` pushed to GitHub.
- Folder skeleton `api/ web/ infra/` in place locally; empty dirs intentionally untracked (no `.gitkeep`) — their first real files land in P0.2–P0.4.
- Quiz passed: git tracks files not dirs; `.env` stays out of history via `.gitignore`.
- **Next: P0.2 — API scaffold (uv project, `/api/v1/health`, ruff + pytest green).**

### 2026-10-10 — P0.2 complete (API scaffold)

- `api/` typed and verified: `pyproject.toml` (exact pins + dev group), `.python-version` (3.13), `uv.lock` (96 packages; pgvector resolves to 0.3.6 — `langchain-postgres` caps it `<0.4`, so no direct pin), `app/main.py` (app factory + `/api/v1/health`), `tests/test_health.py` (async httpx `ASGITransport`, no live server).
- Verify green: `uv run pytest` → 1 passed · `uv run ruff check .` → clean · `uv run mypy` → clean · live `uvicorn` + `curl /api/v1/health` → `{"status":"ok"}`. Hitting `/health` without the prefix → 404, by design.
- Quiz: lockfile-vs-direct-pin distinction solid; filled the gaps on app-factory benefits (test overrides, no import-time side effects) and the `ASGITransport` blind spot — in-process calls skip lifespan/startup hooks (a future DB-pool init needs a lifespan-aware test).
- Editor note: basedpyright's `reportImplicitRelativeImport` misreads the pytest `pythonpath=["."]` layout; disabled editor-locally in gitignored `.vscode/settings.json`.
- **Next: P0.3 — local infra (docker-compose pgvector + `.env.example`).**

### 2026-10-10 — Workflow amendment: quiz step deferred (owner directive)

- Time crunch: the 3-question quiz moves from per-slice to **post-project review**. Slices now close on **typed + verification green + committed**.
- Questions are banked per slice in [`docs/quiz-bank.md`](docs/quiz-bank.md) (P0.2 included, 2 gaps marked for revisit); on-demand rounds anytime via "quiz me".
- Interview-facing notes stay captured as we go (§11 + ADRs from P1), so the end-of-project discussion/interview pass stays cheap.

## 12. Docs map

| File | Purpose |
|---|---|
| [`docs/prd.md`](docs/prd.md) | What & why: users, stories with acceptance criteria, non-goals, metrics |
| [`docs/technical-design.md`](docs/technical-design.md) | How: architecture, data model, API, ingestion + retrieval design, decisions, risks |
| [`docs/tasks.md`](docs/tasks.md) | Every slice with goal, deliverables, acceptance criteria, verify commands |
| `CLAUDE.md` | This file — SSOT: workflow, conventions, roadmap status, progress log |
| [`AGENTS.md`](AGENTS.md) | Agent entry point — defers here |
| `docs/adr/` | Decision records (first entries during P1–P2) |

## 13. Pre-submission checklist

- [ ] Public GitHub repository (clean history, no secrets)
- [ ] Live deployment working from a clean browser (web + api + Neon)
- [ ] README complete: setup, architecture, retrieval flow, env vars
- [ ] Demo video: features, end-to-end, technical decisions, followable
- [ ] Rubric walk-through: each of the 10 items mapped to a moment in app/video (see §2)
- [ ] All five source types demoed; citations clickable for each
- [ ] `.env.example` current; `.env` never committed
- [ ] Bonus features clearly marked ⭐ if shipped
