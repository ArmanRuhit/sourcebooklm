# SourcebookLM — Working Notes (CLAUDE.md)

**Read me first.** Single source of truth for `sourcebooklm`: mission, rubric analysis, architecture, conventions, pairing workflow, roadmap, and the live progress log. [`AGENTS.md`](AGENTS.md) defers here.

Cohort rules live in [`../../CLAUDE.md`](../../CLAUDE.md) (Codecrafters format: brief → attempt → hints → verify). **Exception — owner directive (2026-10-08):** this project runs in **pair-typing mode** (§7 — the owner wants the full per-slice code in chat to type by hand). The Codecrafters default does not apply here. **Amendment (2026-10-10):** per-slice quizzes are deferred to post-project review — see §7.1 step 5 ([`docs/quiz-bank.md`](docs/quiz-bank.md)).

Last updated: 2026-10-28 · Status: **P2.7 complete — sources can be re-indexed, deleted (rows + vectors), and failed jobs retried, with 2s status polling; Phase 2 is closed and P3.1 (retriever) is up next**

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
- [x] P0.3 Local infra: docker-compose pgvector, `.env.example`
- [x] P0.4 Web scaffold: Next 16 + Tailwind + shadcn, page showing API health

*Exit:* `docker compose up -d` + `uv run uvicorn` serves health; `bun dev` shows it; both test/lint suites green.

### Phase 1 — Notebooks & data core (P1)

- [x] P1.1 Schema + migrations: all tables + pgvector extension
- [x] P1.2 Notebooks CRUD API + tests
- [x] P1.3 Notebooks UI (list, create, rename, delete, empty state) + generated API types
- [x] P1.4 Notebook page shell (sources panel + chat area placeholders)

*Exit:* full notebook CRUD from the browser, persisted in Postgres, typed API client wired.

### Phase 2 — Ingestion pipeline (P2) — *rubric item 2 (20)*

- [x] P2.1 Source API + worker skeleton (status machine, claim loop, crash recovery)
- [x] P2.2 Text source end-to-end: chunk → embed → pgvector → `ready`
- [x] P2.3 PDF: upload, bytea storage, file serving, viewer opens at page
- [x] P2.4 Website URL extraction
- [x] P2.5 YouTube transcript extraction (timestamped segments)
- [x] P2.6 VTT transcript parsing
- [x] P2.7 Remove / re-index / failure states + status polling UI

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

### 2026-10-10 — P0.3 complete (local infra)

- `infra/docker-compose.yml`: `pgvector/pgvector:pg17` service `db`, named volume `pgdata`, `pg_isready` healthcheck (5s/3s/10). pg18 deliberately avoided (data-dir layout change); the **Python** pgvector package stays indirect (see P0.2 note).
- `api/.env.example`: committed template for all 9 env vars; real values go to gitignored `api/.env` at P1. `OPENAI_CHAT_MODEL=gpt-5-mini` is provisional — re-confirm at P3.2.
- Caught before first boot: volume mount typo (`/var/lib/postgresql/dataa`) — valid YAML, passes `compose config` and healthcheck, but would silently keep data in an anonymous volume; fixed to `/var/lib/postgresql/data`.
- Verify green: `docker compose ps` → `sourcebooklm-db-1 … (healthy)`; in-container psql → PostgreSQL 17.11; `vector 0.8.7` listed as available → `CREATE EXTENSION` + `\dx` shows it. DB left running for P1.
- Gitignore re-verified in a scratch repo: `api/.env.example` committable via the `!.env.example` negation; `api/.env` stays ignored.
- **Next: P0.4 — web scaffold (Next 16 + Tailwind + shadcn, page showing API health).**

### 2026-10-10 — P0.4 complete (web scaffold)

- `web/`: `create-next-app@16.4.0` (Next 16.4.0 / React 19.3.0, TS, ESLint, Tailwind 4, App Router, `src/`, `@/*` alias, bun) + `shadcn@4.21.4 init` (base-nova preset, neutral, lucide, `cn` helper; theme tokens in `globals.css`).
- `web/src/app/page.tsx`: client-side health card — fetches `${NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/health`; union-typed state (`checking | ok | error`) + `cancelled` cleanup flag. Review caught a dark-mode color slip (`dark:text-green-400` → `dark:text-red-400`), fixed before commit.
- `api/app/main.py`: `CORSMiddleware` with `allow_origins=[WEB_ORIGIN]` (localhost:3000 constant; TODO: move to settings in P1); no credentials until auth exists.
- Verify green: curl shows `access-control-allow-origin: http://localhost:3000`; ruff + mypy + pytest (1 passed); browser renders **API: ok**; `bun run build` passes (Next 16 Turbopack).
- Next 16 generates `web/AGENTS.md` (points agents at its bundled docs) — committed with the tree.
- **Next: P1.1 — Alembic + initial migration (`CREATE EXTENSION vector` + 6 tables: notebooks, sources, source_files, source_contents, conversations, messages).**

### 2026-10-11 — P1.1 in progress (checkpoint — session pause)

- `api/app/config.py`: pydantic-settings `Settings` covering every `.env.example` var; `database_url` required through a `field_validator`. Basedpyright `reportCallIssue` fight: the checker sees only the synthesized `__init__`, not env/.env values — fixed with `str = ""` + validator (also caught a `max_upload_md` → `max_upload_mb` silent-override typo). `.env` created from the example (gitignored).
- `api/app/db.py`: async engine (`pool_pre_ping=True`) + `async_sessionmaker(expire_on_commit=False)` + `get_session` FastAPI dependency. ruff green after one autofix pass (stray `sqlalchemy.false` import + import grouping).
- Verify: basedpyright 0 diagnostics on both files; mypy green (4 source files); pytest 1 passed.
- Local DB container is stopped — resume verify steps with `docker compose -f infra/docker-compose.yml up -d`.
- **Next: `models.py` (6 tables per design §3.1) → Alembic init + custom `env.py` + `alembic.ini` tweak → migration `0001` autogenerated (+ `CREATE EXTENSION IF NOT EXISTS vector`) → `main.py` CORS via settings + `tests/test_db.py` → full verify, then close P1.1 (bank quiz questions in `docs/quiz-bank.md`).**

### 2026-10-17 — P1.1 checkpoint 2 (models + Alembic scaffold)

- `api/app/models.py`: all six tables per design §3.1 — UUID PKs (`gen_random_uuid()`), `timestamptz` server defaults, text + CHECK status/stage/role, JSONB `config` + `citations`, cascade FKs, deterministic constraint names via `MetaData(naming_convention=...)`. Blob relationships (`Source.file` / `Source.content`) are `lazy="raise"` so a forgotten eager load fails loudly.
- Pyright fix: `SourceFile.bytes` self-referenced the class attribute in `Mapped[bytes]` → Python attr renamed `file_bytes`, DB column kept as `bytes` via `mapped_column("bytes", LargeBinary)`. `api/pyrightconfig.json` points Pyright at `api/.venv` (monorepo root does not auto-detect a nested venv).
- Alembic: `alembic init -t async alembic`; `env.py` injects `DATABASE_URL` from typed settings (`%%`-escaped for ConfigParser), targets `Base.metadata`, and runs migrations through an async engine + `connection.run_sync`. Placeholder URL in `alembic.ini` neutralized; `versions/.gitkeep` keeps the empty dir on clone.
- Ruff: `alembic` marked `known-third-party` — the local `alembic/` directory otherwise shadows the installed package. `ruff format` applied to `models.py` + `env.py`.
- Verify green: `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy app` · `uv run pytest -q` → 1 passed. DB not needed for these checks.
- **Next: autogenerate migration `0001` (+ `CREATE EXTENSION IF NOT EXISTS vector`) → `alembic upgrade head` / `downgrade base` on docker Postgres → `main.py` CORS via settings + `tests/test_db.py` → close P1.1 (bank quiz questions).**

### 2026-10-26 — P1.1 complete (schema + migrations)

- **Migration `001_initial_schema`**: autogenerated from the models, then hand-edited — `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` is the first upgrade statement; downgrade drops only the six app tables (extension deliberately left in place). Revision id `001` (ids are opaque; fine).
- **CORS from settings**: `api/app/main.py` now reads `settings.web_origin`; the hardcoded `WEB_ORIGIN` constant and its TODO are gone.
- **DB connectivity test**: `api/tests/test_db.py` — `SELECT 1` through the async engine, then `engine.dispose()` (pytest gives each async test a fresh event loop; disposing keeps the pool from leaking across loops).
- **Verify evidence**: `alembic upgrade head` applies `001`; `\dt` shows 6 app tables + `alembic_version`; `alembic downgrade base` clean (only `alembic_version` remains); re-upgrade ok; `\dx` shows `vector 0.8.7`; `ruff check` / `ruff format --check` / `mypy` green; `pytest -q` → 2 passed.
- Review nits caught by tooling pre-commit: I001 import grouping in `main.py`, a stray `from unittest import result` in `test_db.py`, a trailing-whitespace format pass — all auto-fixed.
- **Next: P1.2 — Notebooks CRUD API** (schemas + service + router, tests against the docker DB).

### 2026-10-26 — P1.2 in progress (checkpoint — session pause)

- **Schemas**: `api/app/schemas.py` — `NotebookName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]`; `NotebookCreate` / `NotebookUpdate` (`name` only); `NotebookRead` with `from_attributes=True`. Lesson: an f-string is not a docstring (ruff `B021`) — and an f-string docstring containing `{notebook_id}` becomes an undefined-name error at import.
- **Service layer**: `api/app/services/notebooks.py` — `create` / `list_all` (newest `updated_at` first) / `get` / `rename` / `delete`; no HTTP imports; commit + refresh after writes; deletes rely on DB `ON DELETE CASCADE`.
- **Package markers**: `app/services/__init__.py`, `app/routers/__init__.py` created.
- **Review catch**: `session.add(Notebook)` (the class) instead of `session.add(notebook)` (the instance) — a live runtime bug the formatter/linter can't see; fixed during wrap-up. Also removed the duplicate `schema.py` (kept `schemas.py`) and its stray f-string.
- **Verify (after cleanup)**: ruff check + format green, mypy green, `pytest -q` → 2 passed (notebook endpoint tests arrive with the router).
- **Next: P1.2 files 3–5** — `routers/notebooks.py` (5 endpoints, 201/204, `{detail}` 404s), `main.py` `include_router` diff, `tests/test_notebooks.py` (7 tests: happy path, 404s, 422 validation, 100-char boundary, cascade) → full verify + slice close.

### 2026-10-28 — P1.2 complete (notebooks CRUD API)

- **Layers**: `schemas.py` (contracts: strip + 1–100 via `StringConstraints`), `services/notebooks.py` (create/list/get/rename/delete, no HTTP imports — reusable by the Phase-2 worker), `routers/notebooks.py` (5 endpoints under `/api/v1/notebooks`; `SessionDep`, `_get_or_404`, 200/201/204).
- **Wiring**: `main.py` mounts the router with `prefix=API_PREFIX`; CORS stays settings-driven.
- **Tests** (`tests/test_notebooks.py`, 7): CRUD happy path incl. whitespace strip; 404 set for GET/PATCH/DELETE; 422 for invalid names (`""`, blank, 101 chars); 100-char boundary creates; cascade proof — insert a `Source` directly, delete the notebook via API, the source is gone.
- **Verify evidence**: `pytest -q` → 9 passed; `mypy` → 10 source files; `ruff check` green (one indent nit in the new test file reformatted); live curl smoke on port 8000: POST 201 (name stripped) → GET list/one 200 → PATCH 200 → DELETE 204 → GET 404.
- Review catches: duplicate `schema.py` twin removed; f-string "docstrings" converted (`{id}` would import-error); `session.add(Notebook)` class-vs-instance bug fixed at checkpoint.
- **Next: P1.3 — Notebooks UI** (list/create/rename/delete pages + generated TS client via `openapi-typescript`).

### 2026-10-28 — P1.3 complete (notebooks UI)

- **Typed client**: `web/src/lib/api-types.ts` generated from the live `/openapi.json`; `web/src/lib/api.ts` wraps fetch with `ApiError` (parses FastAPI `{detail}`, handles 204), `list/create/rename/delete` notebooks. Fixed three bugs in the hand-typed first pass: template literal missing `$` before `{API_URL}` (relative URL), default port `8080`, and DELETE carrying a `{name}` body.
- **UI**: `/notebooks` list with a four-state machine (`loading` skeleton → `error` + retry → `empty` CTA → `ready` grid); shared `NotebookNameDialog` for create + rename; `DeleteNotebookDialog` confirm; `NotebookCard` with icon actions; `AppHeader`; root `/` now redirects to `/notebooks` and the P0.4 health card is retired.
- **State-reset pattern**: React's `set-state-in-effect` lint rule rejected resetting dialog state in effects — dialogs now mount only while open, so a remount gives a clean form (create) or the current name (rename).
- **Verify evidence**: `bun run lint` clean · `bunx tsc --noEmit` clean · `bun run build` green (routes `/`, `/_not-found`, `/notebooks`) · browser pass: empty state → create → rename → delete → empty again, API confirmed `[]`; 3 seeded notebooks survive reload; no console errors.
- Next 16.4.0 prints a security-advisory upgrade nudge on each fresh `next build` / `next dev`; deferred because the stack is pinned in §5 — revisit deliberately at P6.1.
- **Next: P1.4 — Notebook page shell** (route `/notebooks/[id]`; sources panel + chat area placeholders; unknown id → not found; stacked on mobile).

### 2026-10-28 — P1.4 complete (notebook workspace shell)

- **Route**: `/notebooks/[id]` client page; each `NotebookCard` title links to it. Four states: `loading` skeleton → `missing` (API 404, or 422 for a malformed UUID) → `error` + retry → `ready`.
- **Shell**: responsive `grid` — one column on mobile (sources stacked above chat), `320px 1fr` at `lg`; Sources panel with a disabled Add button and Phase 2 copy; Chat panel with a disabled composer. Real source/chat wiring lands in P2/P3.
- **Next 16 Cache Components**: `useParams()` in a client component must sit under `<Suspense>`; split the page into `NotebookPage` (Suspense wrapper) + `NotebookPageContent`. Base UI's `Button render={<Link/>}` also needs `nativeButton={false}` so the anchor keeps link semantics and the console stays clean.
- **Verify evidence**: `bun run lint` clean · `bunx tsc --noEmit` clean · `bun run build` green (`/notebooks/[id]` = Partial Prerender) · browser pass: card → shell, valid-but-unknown UUID → "Notebook not found", malformed id → same, back button → list; narrow viewport stacks panels; no JS exceptions (only the expected 404/422 resource logs).
- **Next: P2.1 — Source API + worker skeleton** (status machine, `FOR UPDATE SKIP LOCKED` claim loop, startup requeue, stub text processor, tests).

### 2026-10-28 — P2.1 complete (source API + worker skeleton)

- **API**: `GET/POST /api/v1/notebooks/{id}/sources`, `GET/DELETE /api/v1/sources/{id}`. Create is a multipart form (`python-multipart` added) validated by `SourceCreate`; P2.1 widens `kind` to `text` only, so later kinds arrive with their extractors. Text is stored in `source_contents` at create time (extraction is a passthrough); the title falls back to the first non-empty line.
- **Shared deps**: `routers/deps.py` now owns `SessionDep`, `get_notebook_or_404`, and `NotebookDep`; the notebooks router was simplified to use them, so sources get the same 404 behavior without copy-paste.
- **Worker**: `services/ingestion/worker.py` uses the `sources` table as the queue — claim the oldest `queued` row with `FOR UPDATE SKIP LOCKED`, flip to `processing`/`extracting`, commit (releasing the lock), then walk `chunking → embedding → indexing → ready`. Failures land in `failed` + `error`; the loop logs and survives. Startup requeues every stale `processing` row before the polling task starts.
- **Lifespan**: `main.py` runs requeue + `run_worker()` as an app-lifespan task and cancels it cleanly on shutdown. `process_next()` is directly testable without a server.
- **Tests** (12 new, 21 total): source CRUD + default title + 404s + validation (empty text, wrong kind, 201-char title); worker ready path/`char_count`, requeue recovery, failure without content, concurrent claims distinct, and a held row lock proving `SKIP LOCKED` returns nothing. All green: `ruff check` + `ruff format --check` + `mypy` (15 files) + `pytest -q`.
- **Manual evidence**: multipart POST → `queued`; poll → `ready`, `char_count=77`. Inserted a `processing`/`embedding` row, restarted the API; log showed `requeued 1 interrupted source(s)` and the source reached `ready` (`char_count=34`). Regenerated `web/src/lib/api-types.ts` from the expanded OpenAPI schema (242 lines added); `tsc --noEmit` clean.
- **Next: P2.2 — text end-to-end** (recursive chunker 1000/150, OpenAI embeddings, PGVector `chunks` init + HNSW, metadata, `chunk_count`, search smoke script).

### 2026-10-28 — P2.2 complete (text → chunk → embed → index)

- **Chunker**: `ingestion/chunker.py` uses `RecursiveCharacterTextSplitter` at 1000 chars / 150 overlap with `add_start_index`; every `Chunk` carries `index`, `char_start`, and `char_end`, so a citation can point at the exact snapshot range.
- **LangGraph**: `ingestion/graph.py` compiles `extract → chunk → embed_and_index` over `IngestState`. Each node commits its stage for the polling UI; exceptions bubble to the worker boundary, which marks the source `failed`, stores a safe message, and deletes partial vectors. The worker still owns the DB queue and `SKIP LOCKED` claim.
- **Embeddings**: `services/vector_store.py` builds `OpenAIEmbeddings` (`text-embedding-3-small`, `EMBEDDING_DIMENSIONS=1536`, 3 retries) and fails with a clear `EmbeddingConfigError` when the key is still the `sk-...` placeholder. Startup logs that warning instead of crashing; the API stays healthy and a source fails with the same human-readable message.
- **PGVector**: single `chunks` collection; tables created by `langchain-postgres`, then a cosine HNSW index (`ix_langchain_pg_embedding_hnsw`) is created idempotently at startup and before use. Metadata: `notebook_id`, `source_id`, `source_type`, `chunk_index`, `title`, `char_start`, `char_end`. Search always applies `filter={"notebook_id": ...}`.
- **Delete invariant**: `services.sources.delete` now removes a source's vectors before the row. `langchain-postgres 0.0.19`'s `adelete(filter=...)` silently ignores filters, so deletion is direct SQL on `cmetadata->>'source_id'`; re-index is delete-then-add with deterministic `source_id:index` IDs.
- **Tests** (9 new, 30 total): chunk size/overlap/offsets + empty rejection; notebook-filter isolation; re-index replaces rather than duplicates; HNSW index exists; delete removes vectors; worker pipeline writes searchable chunks. `ruff check`, `ruff format --check`, `mypy` (21 files), and `pytest -q` all green.
- **Manual evidence**: with deterministic test embeddings, a 1608-char text source reached `ready` with `chunk_count=2`; filtered search returned both chunks (best distance 0.8835). Live API without a key: `queued → failed` with “OPENAI_API_KEY is not configured…”. With a real key: a ~1.1k-char source reached `ready` (`chunk_count=2`) in 9s, and `smoke_search` returned both chunks (distances 0.4715 / 0.6141) with correct metadata. `langchain_pg_*` tables and the HNSW index exist; test vectors cleaned to zero.
- **Real-key smoke is green** (2026-10-28). P2.7 still owns the re-index/retry UX.
- **Next: P2.3 — PDF** (multipart upload cap + type check, `source_files` bytea, per-page extractor, streaming file endpoint, PDF viewer opening at a page).

### 2026-10-28 — P2.3 complete (PDF ingestion + viewer)

- **Upload API**: `POST /notebooks/{id}/sources` now accepts `kind=pdf` with a multipart `file` (`pypdf` added). It caps at `MAX_UPLOAD_MB` (20), rejects empty/non-PDF payloads by sniffing `%PDF-` rather than trusting the browser type, returns `413` for oversize, `422` for bad content, and stores bytes in `source_files.bytea` with a sanitized filename. `GET /sources/{id}/file` streams 64 KiB chunks with `Content-Length`, inline `Content-Disposition`, `private` caching, and `nosniff`.
- **Extraction**: `ingestion/pdf.py` reads page text with pypdf; password-protected, corrupt, and scan-only PDFs become clear `IngestionError`s. `_extract` saves a page snapshot to `source_contents.pages` and joins the text for the existing search snapshot.
- **Page-aware chunks**: `split_pages` chunks each page independently so overlap never crosses a page boundary; offsets stay page-relative and every vector carries `page`. This is what lets a citation open the viewer at the cited page (wired in P3).
- **Workspace UI**: Sources panel lists real sources with status dots, polling every 2 s while anything is queued/processing; the Add dialog shows all five tiles but only PDF is active; the PDF viewer uses `react-pdf` + a bundled pdf.js worker, with page controls and a third column from `xl` up (stacked on mobile). Viewer starts at page 1 today; citation-driven pages arrive with chat.
- **Polling bug fixed**: the 2 s chain stopped once the pre-upload list was settled, so a newly added source stayed “Queued” until reload. `addSource` now restarts the polling effect via `reloadKey`; verified a third upload went Queued → Ready in 2.4 s with no reload.
- **Tests** (14 new, 44 total): page extraction/encryption/corruption/scan-only; upload size/type/magic/title/404 cases; streamed bytes + headers; PDF pipeline page metadata; corrupt PDF failure. `ruff check`, `ruff format --check`, `mypy` (22 files), `pytest -q` all green.
- **Manual evidence**: live 995 B PDF → `ready` in ~2 s with `chunk_count=2`, `char_count=161`; streamed file byte-identical with correct headers; browser viewer showed “Page 1 of 2” → “Page 2 of 2” and the extracted text; upload through the dialog rendered the new source and polling settled it without a refresh. Sources cleaned up; list back to `[]`.
- **Next: P2.4 — website URL ingestion** (fetch with timeout/size guard, HTML → readable text, per-source metadata, same pipeline, UI tile live).

### 2026-10-28 — P2.4 complete (website URL ingestion)

- **URL API**: `POST /notebooks/{id}/sources` accepts `kind=url` + a form `url` validated by `SourceUrlCreate` (`HttpUrl`). `create_url` inserts a queued source titled from the hostname (or a custom title) and stores `{url, custom_title}`. `GET /sources/{id}/content` returns the stored text/pages snapshot for any source, which the viewer reuses.
- **SSRF guard**: before fetching, `validate_public_url` requires http(s), no credentials, no localhost/`.local`, and resolves every address via `getaddrinfo`, rejecting non-global IPs. This blocks obvious private-network targets; redirects are not re-validated hop-by-hop, which is documented as the remaining gap.
- **Extraction**: `fetch_article` uses LangChain `WebBaseLoader` with a 15 s timeout, a project User-Agent, and `bs_get_text_kwargs={"separator": "\n"}` so headings/paragraphs don't concatenate. It captures the `<title>`, meta description, and final URL, and maps timeouts/HTTP errors/empty pages to explicit `IngestionError`s. `bs4` was missing from the initial dependency set — live smoke caught it, and it plus a local-HTTP test now guard the real loader path.
- **Pipeline**: the URL branch of `_extract` fetches off the event loop, writes a `source_contents` text snapshot, updates `char_count`, replaces a hostname title with the page title unless the user supplied one, stores `final_url`/`description` in `config`, and then uses the same chunk → embed → index path.
- **Web**: the Web link tile is live in the Add dialog; the URL form normalizes and validates in the browser; URL rows show the hostname and open a read-only text viewer with the original link. The sources list now opens any ready source (PDF or text).
- **Tests** (16 new, 60 total): public/private URL validation, URL creation and config, invalid URL cases, content endpoint + 404, a real local-HTML `WebBaseLoader` round trip, and mocked URL pipeline success/failure with vector metadata. `ruff check`, `ruff format --check`, `mypy` (23 files), and `pytest -q` are green.
- **Manual evidence**: live ingest of `https://example.com` reached `ready` in ~1 s with `chunk_count=1`, `char_count=170`, title “Example Domain”, and a newline-separated text snapshot; the viewer rendered the text and an `Open original` link to `https://example.com/`. Adding a second link through the dialog reached Ready without a refresh; both smoke sources were deleted (list `[]`).
- **Next: P2.5 — YouTube** (`youtube-transcript-api` segments with start/duration, oEmbed title, timestamped chunk metadata, watch/youtu.be/shorts URL forms).

### 2026-10-28 — P2.5 complete (YouTube transcripts)

- **URL handling**: `extract_video_id` accepts `watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/live/`, and `/v/` forms on an allowlist of YouTube hosts. Invalid or non-video URLs become a 422 at create time, before anything is queued.
- **Extraction**: `fetch_transcript` calls `youtube-transcript-api` for English variants and keeps `(text, start, end)` cues; missing/disabled/age-restricted/blocked transcripts map to specific `IngestionError` messages. The title comes from YouTube oEmbed and is best-effort — a failed title lookup never fails the source.
- **Pipeline**: `_extract` stores the joined transcript as `source_contents.text`, the cue list as `segments`, and `char_count`; it replaces the placeholder title (“YouTube video”) with the video title unless the user supplied one, and records `final_url`/`video_id`. `split_transcript` packs cues up to 1000 chars without splitting one, adds a one-cue overlap, and stamps each chunk with `start_seconds`/`end_seconds`; PGVector metadata carries both.
- **Web**: the YouTube tile and URL form are live. A ready video opens an embedded player plus a transcript list; clicking a cue seeks the iframe (`?start=…`), and the active cue is highlighted. Video rows show “YouTube” and open any ready source.
- **Tests** (17 new, 77 total): URL-form parsing/rejections; source creation and config; mocked transcript pipeline success/failure with segment and vector metadata; timed-chunk packing, one-cue overlap, offsets, and empty-cue failure. `ruff check`, `ruff format --check`, `mypy` (23 files), and `pytest -q` are green.
- **Manual evidence**: live ingest of `youtube.com/watch?v=jNQXAC9IVRw` reached `ready` in ~5 s with `chunk_count=1`, `char_count=217`, 6 segments, and title “Me at the zoo”. The viewer rendered the player + 6 cues; clicking `0:01` and `0:12` changed the iframe `start` parameter accordingly, with no console errors. Source deleted; list back to `[]`.
- **Next: P2.6 — VTT transcript parsing** (timestamped cues, same chunk path, upload + viewer).

### 2026-10-28 — P2.6 complete (VTT transcripts)

- **Parser**: `services/ingestion/vtt.py` decodes UTF-8 (BOM allowed), requires the `WEBVTT` header, skips `NOTE`/`STYLE`/`REGION` blocks, handles cue identifiers and timestamp settings, strips inline tags, unescapes entities, and accepts both `MM:SS.mmm` and `HH:MM:SS.mmm`. Missing headers, bad timestamps, backwards cues, and empty files raise `IngestionError`; malformed uploads fail in the worker rather than at request time.
- **Upload**: `POST /notebooks/{id}/sources` now accepts `kind=vtt` with a required `.vtt` file. It enforces the 20 MB cap (413), checks the `WEBVTT` magic (422), stores the original bytes in `source_files` as `text/vtt; charset=utf-8`, and falls back to the filename stem for the title. `GET /sources/{id}/file` streams it unchanged.
- **Pipeline**: the VTT branch of `_extract` parses the stored bytes off the event loop, writes `source_contents.text` (newline-joined cues) and `segments`, sets `char_count`/stage `chunking`, then reuses `split_transcript` and the existing start/end metadata path. No new chunking or vector code.
- **Web**: the VTT tile is live in the Add dialog with a `.vtt` file picker and 20 MB check; VTT rows show “VTT” and open a transcript viewer with cue timestamps, cue count, fallback text, and an `Open original` link. `readSegments` moved into `lib/segments.ts` so YouTube and VTT viewers share the same defensive parsing.
- **Tests** (9 new, 86 total): parser cues/settings/markup/BOM/CRLF, malformed headers/timestamps/backwards cues/empty files, upload + streaming, `.txt`/wrong-magic/empty/missing/oversize rejection, a full VTT pipeline with segment + vector metadata, and a malformed file landing in `failed`. `ruff check`, `ruff format --check`, `mypy` (24 files), and `pytest -q` are green.
- **Manual evidence**: live upload of a two-cue VTT reached `ready` in ~1 s with `chunk_count=1`, `char_count=101`, and segments `1.0–4.5` / `5.0–9.25`. The browser rendered “2 transcript cues”, both timestamps, and the original-file link; adding a second VTT through the dialog reached Ready via polling without a refresh, and its viewer showed “1 transcript cue”. Both smoke sources were deleted; the list returned to `[]`.
- **Next: P2.7 — remove / re-index / failure UX** (delete action, retry, error states, polling polish).

### 2026-10-28 — P2.7 complete (delete, re-index, retry)

- **API**: `POST /api/v1/sources/{id}/reindex` (202) deletes the source's vectors, resets `status=queued`, `stage/error=null`, `chunk_count=0`, and lets the worker rebuild. It returns 409 while a source is `processing` so one source cannot be double-claimed. `DELETE` keeps its 204 and now has lifecycle test coverage proving vectors are gone.
- **Re-index is idempotent**: the endpoint deletes vectors before queueing, and the index graph deletes again before adding, so repeated calls leave exactly one vector per chunk. Tests call reindex twice and assert one unique `chunk_index`.
- **Failure recovery**: a failed URL source retries through the same endpoint and reaches `ready` once the extractor is fixed. The UI shows the failure message plus Retry; re-index and delete are available on every source.
- **Web**: source rows gained an action bar (Ready → Re-index, Failed → Retry, always Delete) with per-row busy spinners; confirm dialog names the source and explains that text and indexed chunks are removed. Deleting the open source closes the viewer. `useSources` now exposes `updateSource`/`removeSource` and restarts polling after mutations, so re-index is visible without a refresh.
- **Tests** (5 new, 91 total): re-index twice with unique vectors; API delete removes vectors and GET 404s; 409 while processing; failed → retry → ready; missing source 404. `ruff check`, `ruff format --check`, `mypy` (24 files), and `pytest -q` are green.
- **Manual evidence**: a ready text source re-indexed through the UI (`Queued` → `Ready`), then delete confirmed removal (API list `[]`, vector count 0). A bad URL produced `failed` with “Could not resolve that URL's host”; Retry returned it to `Queued` and back to `failed` with the same message, with no console errors. Smoke source deleted afterward.
- **Next: P3.1 — retriever module** (notebook-filtered similarity search k=12 → MMR → 6, tests).

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
