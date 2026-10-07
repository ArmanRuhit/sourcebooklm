# Tasks — SourcebookLM

Slice-by-slice breakdown for the roadmap in [CLAUDE.md §8](../CLAUDE.md). Workflow rules (pair-typing, quiz, verify) live in [CLAUDE.md §7](../CLAUDE.md); architecture context in [technical-design.md](technical-design.md).

**Definition of done (every slice):** code typed by owner → verify commands green → quiz answered → committed → `CLAUDE.md` §11 updated.

Slice IDs match the roadmap exactly (`P<phase>.<n>`). Checkboxes live in CLAUDE.md — this file defines *what done means*.

---

## Phase 0 — Foundation

### P0.1 — Repo init
- **Goal**: git repo with the agreed skeleton, ready to hold both apps.
- **Deliverables**: `git init`; `.gitignore` (Python/Node/env/OS); folder skeleton `api/ web/ infra/ docs/`; README placeholder; first commit.
- **Acceptance criteria**: repo exists with one commit; `git status` clean; layout matches CLAUDE.md §6 (minus code files).
- **Verify**: `git log --oneline` (1 commit) · `git status` (clean).
- **Depends**: —

### P0.2 — API scaffold
- **Goal**: runnable FastAPI app with pinned deps, lint, and a first test.
- **Deliverables**: `uv init`; `pyproject.toml` with pinned deps (fastapi, uvicorn, sqlalchemy[asyncio], psycopg[binary], alembic, pydantic-settings, langchain + integration packages, langgraph, langchain-postgres, pgvector, sse-starlette; dev: ruff, pytest, pytest-asyncio, httpx, mypy); `app/main.py` with `/api/v1/health`; ruff + pytest config.
- **Acceptance criteria**: server responds `{"status":"ok"}`; ruff clean; pytest green (1 health test).
- **Verify**: `uv run uvicorn app.main:app` + `curl localhost:8000/api/v1/health` · `uv run pytest` · `uv run ruff check .`.
- **Depends**: P0.1.

### P0.3 — Local infra
- **Goal**: one-command local Postgres with pgvector.
- **Deliverables**: `infra/docker-compose.yml` (pgvector image, volume, healthcheck); `.env.example` (DATABASE_URL, OPENAI_API_KEY, DEEPSEEK_API_KEY, CHAT_PROVIDER, OPENAI_CHAT_MODEL, DEEPSEEK_CHAT_MODEL, EMBEDDING_MODEL, WEB_ORIGIN, MAX_UPLOAD_MB).
- **Acceptance criteria**: `docker compose up -d` → healthy; `psql` connects; `CREATE EXTENSION vector` succeeds.
- **Verify**: `docker compose ps` (healthy) · `psql $DATABASE_URL -c '\dx'` after P1.1 migration.
- **Depends**: P0.1.

### P0.4 — Web scaffold
- **Goal**: Next.js app that talks to the API.
- **Deliverables**: create-next-app (Next 16.4.x, TS, Tailwind, App Router, `src/`, bun); shadcn/ui init; landing page fetching `/api/v1/health` (server-side or client) rendering "API: ok"; CORS configured on API for `http://localhost:3000`.
- **Acceptance criteria**: `bun dev` page shows API ok; `bun run build` passes.
- **Verify**: `bun dev` + browser check · `bun run build`.
- **Depends**: P0.2.

**Phase exit**: `docker compose up -d` + `uv run uvicorn …` + `bun dev` all work; both test suites green.

---

## Phase 1 — Notebooks & data core

### P1.1 — Schema + migrations
- **Goal**: every table the app will need, via Alembic.
- **Deliverables**: Alembic setup; migration 1: `CREATE EXTENSION IF NOT EXISTS vector`; tables `notebooks`, `sources`, `source_files`, `source_contents`, `conversations`, `messages` (columns/indexes per design doc §3).
- **Acceptance criteria**: `alembic upgrade head` on fresh DB creates all tables; `alembic downgrade base` clean; app connects with async engine.
- **Verify**: `uv run alembic upgrade head` · `psql -c '\dt'` (6 tables) · `uv run alembic downgrade base && uv run alembic upgrade head`.
- **Depends**: P0.2, P0.3.

### P1.2 — Notebooks CRUD API
- **Goal**: full notebook management over HTTP.
- **Deliverables**: `routers/notebooks.py`; pydantic schemas; service layer; tests (create/list/get/rename/delete, 404s, validation).
- **Acceptance criteria**: CRUD works; delete cascades; name validation 1–100; tests green against docker DB.
- **Verify**: `uv run pytest tests/test_notebooks.py` · `curl` smoke of each endpoint.
- **Depends**: P1.1.

### P1.3 — Notebooks UI
- **Goal**: manage notebooks from the browser.
- **Deliverables**: notebooks list page; create dialog; inline rename; delete confirm; empty state; typed API client generated from OpenAPI (`openapi-typescript`).
- **Acceptance criteria**: full CRUD via UI persists across refresh; empty state visible with zero notebooks; no `any` in client types.
- **Verify**: manual browser pass · `bun run build` · `bunx tsc --noEmit`.
- **Depends**: P1.2.

### P1.4 — Notebook page shell
- **Goal**: the two-pane workspace where sources and chat will live.
- **Deliverables**: route `/notebooks/[id]`; left sources panel + right chat area placeholders; breadcrumb back to list.
- **Acceptance criteria**: navigation works; unknown notebook id → not-found state; layout holds on mobile (stacked).
- **Verify**: manual browser pass at desktop + narrow width.
- **Depends**: P1.3.

**Phase exit**: notebooks fully managed from the UI; every query path carries `notebook_id` by construction.

---

## Phase 2 — Ingestion pipeline

### P2.1 — Source API + worker skeleton
- **Goal**: durable job processing with visible statuses before real extraction.
- **Deliverables**: `sources` CRUD-lite API (create/list/delete); status machine (`queued/processing/ready/failed` + `stage`); worker loop in FastAPI lifespan (claim via `FOR UPDATE SKIP LOCKED`, requeue stale `processing` on startup); stub text passthrough processor.
- **Acceptance criteria**: create text source → statuses advance to `ready`; kill API mid-processing → restart recovers to `ready`; two workers never double-process (test or log evidence).
- **Verify**: create source + poll `GET /sources` · restart test manually · `uv run pytest tests/test_worker.py`.
- **Depends**: P1.2.

### P2.2 — Text end-to-end (chunk → embed → index)
- **Goal**: first real RAG path: text becomes searchable vectors.
- **Deliverables**: chunker module (recursive split, 1000/150); embeddings service (OpenAI `text-embedding-3-small`); PGVector collection `chunks` init + HNSW index; metadata per design doc; text extractor fills `source_contents`.
- **Acceptance criteria**: text source → `ready` with `chunk_count`; similarity search script returns expected chunk; metadata filter by `notebook_id` works.
- **Verify**: `uv run pytest tests/test_chunking.py tests/test_indexing.py` · `uv run python -m app.evals.smoke_search --notebook <id> --query "…"`.
- **Depends**: P2.1, P1.1.

### P2.3 — PDF
- **Goal**: upload a PDF and cite its pages.
- **Deliverables**: multipart upload endpoint (cap 20 MB, type check); PDF bytes → `source_files` (bytea); extractor with per-page text + `page` metadata; `GET /sources/{id}/file` streaming; UI: add-PDF flow + right-side viewer panel (PDF.js `react-pdf`) opening at a given page.
- **Acceptance criteria**: upload → `ready`; viewer opens correct page; oversize/wrong type rejected with clear error.
- **Verify**: upload fixture PDF → chat-free check via API + browser viewer.
- **Depends**: P2.2.

### P2.4 — Website URL
- **Goal**: turn an article URL into a source.
- **Deliverables**: URL validation + fetch extractor (LangChain `WebBaseLoader`); title/metadata capture; stored text snapshot for the viewer.
- **Acceptance criteria**: article URL → `ready`; junk URL → `failed` with message; viewer shows stored text.
- **Verify**: ingest 2 real articles; 1 bad URL; check statuses + viewer.
- **Depends**: P2.2.

### P2.5 — YouTube
- **Goal**: video transcript as a timestamped source.
- **Deliverables**: extractor using `youtube-transcript-api` (segments with start/duration) + oEmbed title; transcript chunking that preserves start/end seconds per chunk; URL forms handled (watch, youtu.be, shorts).
- **Acceptance criteria**: video → `ready`; chunks carry start/end times; deterministic failure message when transcripts unavailable.
- **Verify**: ingest 2 videos (one long); inspect metadata via SQL/script.
- **Depends**: P2.2.

### P2.6 — VTT transcript
- **Goal**: uploaded `.vtt` becomes a timestamped source.
- **Deliverables**: WebVTT parser (cues, hours:minutes:seconds.millis); same segment pipeline as YouTube; multipart upload path.
- **Acceptance criteria**: fixture VTT → `ready`; cue times preserved in metadata; malformed file → `failed`.
- **Verify**: `uv run pytest tests/test_vtt.py` · upload fixture in browser.
- **Depends**: P2.2.

### P2.7 — Remove / re-index / failure UX
- **Goal**: sources are fully manageable, failures recoverable.
- **Deliverables**: delete endpoint removing vectors by metadata filter (+ rows); re-index endpoint (delete old vectors → requeue, idempotent); retry button on `failed`; status polling hook in UI (2s while active, stops when settled).
- **Acceptance criteria**: after delete, retrieval never returns that source; re-index twice → no duplicate vectors; failed source retries successfully with a fix (e.g. valid URL).
- **Verify**: integration test for delete/reindex; manual browser pass of polling + retry.
- **Depends**: P2.3–P2.6.

**Phase exit**: all five source types ingest with correct metadata; delete/re-index/retry proven; statuses survive restarts.

---

## Phase 3 — RAG chat

### P3.1 — Retriever module
- **Goal**: notebook-scoped semantic search as a tested service.
- **Deliverables**: `services/rag/retriever.py` (embed query → similarity search k=12 → MMR → 6, filter `notebook_id`); tests on a seeded fixture notebook.
- **Acceptance criteria**: returns expected chunk for fixture queries; never returns another notebook's chunks; unit tests green.
- **Verify**: `uv run pytest tests/test_retriever.py`.
- **Depends**: P2.2, P2.7.

### P3.2 — Streaming query endpoint
- **Goal**: grounded, cited, streamed answers over SSE.
- **Deliverables**: `POST /api/v1/notebooks/{id}/query` returning SSE (`meta → citations → token* → done | error`); citation-constrained prompt (context blocks `[1…n]`, must cite, refuse if empty); provider switch (OpenAI/DeepSeek via env); assistant message persisted with citations snapshot.
- **Acceptance criteria**: `curl -N` streams tokens; answer cites `[n]`; empty notebook → refusal message; no-context question → no invented citations.
- **Verify**: `curl -N -X POST …/query -d '{"question":"…"}'` · pytest for refusal path.
- **Depends**: P3.1.

### P3.3 — Chat UI
- **Goal**: ask questions in the notebook page and watch answers stream.
- **Deliverables**: message list + composer in `/notebooks/[id]`; SSE consumption via `fetch` streams; Markdown rendering; inline citation chips; auto-scroll; stop/regenerate-lite (stop button).
- **Acceptance criteria**: streamed render without reload; chips visible; reload shows persisted history (from P3.5); errors surface as toast.
- **Verify**: browser pass with a seeded notebook.
- **Depends**: P3.2.

### P3.4 — Citation deep-links
- **Goal**: clicking a citation lands on the original moment.
- **Deliverables**: viewer routing from citation payload; PDF → open page (+snippet panel); YouTube → embed player seek to `start_seconds`; text/VTT/URL → highlight chunk text (substring search MVP).
- **Acceptance criteria**: all five types open the right artifact; wrong/no match degrades gracefully (opens source start).
- **Verify**: manual pass, one citation per source type.
- **Depends**: P2.3–P2.6, P3.3.

### P3.5 — History + grounding polish
- **Goal**: conversations feel real and answers refuse safely.
- **Deliverables**: conversation auto-create per notebook; messages endpoint; history hydration on load; refusal wording; Markdown formatting instructions; error events handled in UI.
- **Acceptance criteria**: reload restores full history incl. citation chips; adversarial question with no context refuses; API errors don't break the chat.
- **Verify**: pytest for messages endpoint + manual reload/adversarial pass.
- **Depends**: P3.2.

**Phase exit (demo-safe)**: create notebook → add sources → ask → streamed cited answer → click citations; history persists.

---

## Phase 4 — Retrieval quality

### P4.1 — Eval harness + fixtures
- **Goal**: measurable retrieval, not vibes.
- **Deliverables**: `app/evals/retrieval.py` (seeds fixture notebook, runs Q→expected-source pairs, prints hit@k); 12–15 handcrafted pairs across source types; baseline recorded in progress log.
- **Acceptance criteria**: script runs reproducible; baseline hit-rate documented.
- **Verify**: `uv run python -m app.evals.retrieval`.
- **Depends**: P3.1.

### P4.2 — Retrieval upgrades (measured)
- **Goal**: better chunking + better selection, each step measured against P4.1.
- **Deliverables**: transcript-aware chunk params; MMR tuning; one of query-rewrite / multi-query / LLM-rerank (pick by eval result); final defaults documented.
- **Acceptance criteria**: improvement over baseline recorded (numbers in progress log/ADR); no regression for other types.
- **Verify**: eval script before/after outputs.
- **Depends**: P4.1.

### P4.3 — Highlight fidelity
- **Goal**: citations point *inside* the right spot, not just the right document.
- **Deliverables**: PDF page + snippet side panel (text-layer highlight if the spike succeeds, else documented fallback); transcript cue highlight; text/media chunk highlight using stored offsets or robust substring match.
- **Acceptance criteria**: visible highlight for ≥3 source types; no broken links for the rest.
- **Verify**: manual pass per type + screenshot for README.
- **Depends**: P3.4, P4.2.

**Phase exit**: eval numbers published; citations land with visible highlights in at least 3 types.

---

## Phase 5 — UX & hardening

### P5.1 — UX states pass
- **Goal**: every screen handles loading/empty/error states visibly.
- **Deliverables**: skeletons (lists, sources, chat), empty states (no notebooks / no sources / no messages), disabled-in-flight buttons, toasts, responsive drawer for sources on mobile.
- **Acceptance criteria**: self-run checklist per rubric 7 passes; no layout breaks at 375 px / 1280 px.
- **Verify**: manual pass + `bun run build`.
- **Depends**: P3.5.

### P5.2 — Error/edge hardening
- **Goal**: no unhandled paths in normal misuse.
- **Deliverables**: upload validation (type/size) on both ends; duplicate-source warning; long-question cap; API error envelope honored in UI; backend 500s logged with context.
- **Acceptance criteria**: scripted misuse pass (bad file, bad URL, no transcript, huge question) shows friendly errors; server log has context lines.
- **Verify**: manual misuse pass + `uv run pytest`.
- **Depends**: P5.1.

### P5.3 — ⭐ Accessibility quick pass
- **Goal**: keyboard + screen-reader sanity for forms, dialogs, chat.
- **Deliverables**: focus management in dialogs; labels; `alt`/`aria` on icons; contrast check.
- **Acceptance criteria**: full keyboard flow: create notebook → add source → ask question.
- **Verify**: keyboard-only pass.
- **Depends**: P5.1.

---

## Phase 6 — Deploy & README

### P6.1 — Deploy
- **Goal**: live, stable deployment of all three tiers.
- **Deliverables**: Neon prod DB + migrations applied; Render web service (build `uv sync`, start `alembic upgrade head && uvicorn …`; env vars; pooled DATABASE_URL for runtime, direct for migrations); Vercel project (`NEXT_PUBLIC_API_URL`); CORS `WEB_ORIGIN` set to the real web origin; smoke checklist.
- **Acceptance criteria**: from a clean browser: create notebook → add source → ask → get cited answer on the live URL; no CORS errors.
- **Verify**: live smoke test (all five source types).
- **Depends**: P5.2.

### P6.2 — README + docs final
- **Goal**: a stranger can run and understand it.
- **Deliverables**: README (overview, live link, features + screenshots/GIF, stack table, local setup, env table, architecture diagram, retrieval flow, project structure, roadmap); docs synced with reality.
- **Acceptance criteria**: fresh-clone dry run in a clean directory follows README only, passes.
- **Verify**: `git clone` to /tmp + follow README step-by-step.
- **Depends**: P6.1.

---

## Phase 7 — Demo video & submission

### P7.1 — Demo video
- **Goal**: 5–7 min video covering features, end-to-end flow, and technical decisions.
- **Deliverables**: script built on the three killer flows; recorded; published (unlisted is fine if linkable); link in README.
- **Acceptance criteria**: video shows all 5 source types + citations + one technical deep-dive (ingestion pipeline or retrieval), followable without prior context.
- **Verify**: watch-through against rubric 9 bullets.
- **Depends**: P6.2.

### P7.2 — Submission pass
- **Goal**: everything in the pre-submission checklist verified.
- **Deliverables**: repo public + history clean (no secrets); checklist in CLAUDE.md §13 fully ticked; assignment cross-check against [assignments.md](../assignments.md).
- **Acceptance criteria**: all §13 boxes checked; submission requirements (public repo, live deployment, README, demo video) each demonstrably true.
- **Verify**: §13 pass + a second-person smoke (or fresh browser profile).
- **Depends**: P7.1.

---

## Phase 8 — ⭐ Stretch (after P7 only)

### P8.1 ⭐ — Playlist → learning roadmap
Ingest a YouTube playlist; ordered study plan with timestamp deep-links. *AC*: playlist URL → roadmap of N steps, each linked to its video + start time.

### P8.2 ⭐ — Podcast voice-over
TTS summary of selected sources with inline player. *AC*: generate once → playable audio in the notebook; regenerate works.

### P8.3 ⭐ — Hybrid search + semantic chunking
Postgres FTS + vector hybrid retrieval behind a flag; semantic-chunking experiment measured on the P4.1 eval set. *AC*: either beats baseline and becomes default, or is documented as a rejected experiment (both outcomes are wins).
