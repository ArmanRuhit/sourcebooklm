# PRD — SourcebookLM

Status: draft for build · Owner: project owner · Date: 2026-10-08
Links: [assignment](../assignments.md) · [technical design](technical-design.md) · [tasks](tasks.md) · [CLAUDE.md](../CLAUDE.md)

## 1. Problem & context

The GenAI-with-JS cohort's final project asks for an **AI research assistant inspired by Gemini Notebook**: users organize material into notebooks, feed them sources, and get answers grounded in those sources with inspectable citations. The assignment (see [assignments.md](assignments.md)) is evaluated on a 10-item rubric — ingestion and RAG depth carry the most marks.

Building it is also the learning goal: understand modern RAG end-to-end — extraction, chunking, embeddings, vector search, retrieval quality, grounded prompting, and citation UX — not just call an LLM.

## 2. Users & jobs to be done

- **Persona**: a self-learner/researcher juggling PDFs, articles, lecture videos, and transcript files on overlapping topics.
- **JTBD**: *"When my learning material is scattered across formats, I want one workspace where I can ask questions across it and verify every claim against the original moment, so I can trust what I learn."*
- Single-user at a time (no auth — see non-goals). Everything is public-demo safe.

## 3. Goals

1. Multi-notebook workspace: create, rename, delete; each notebook's knowledge base is isolated.
2. Ingest all five source types: **PDF, plain text, website URL, YouTube video, VTT transcript** — with a visible lifecycle (uploading → indexing → ready) and removal/re-index.
3. Ask natural-language questions; answers are **grounded in the notebook only**, streamed, and **cite sources with `[n]` markers**.
4. Inspect citations: opening a citation lands on the original moment — PDF page, website passage, YouTube timestamp, text/transcript highlight.
5. A codebase and docs that survive scrutiny: clean layering, tests, migrations, decision records.

Non-goals (explicit):

- ❌ Authentication, accounts, multi-user, sharing, collaboration — single-user demo; rubric has no auth item.
- ❌ Native mobile apps, payments, fine-tuning, analytics dashboards.
- ❌ Podcast / learning-roadmap bonus features are ⭐ stretch only (Phase 8, after submission-ready).

## 4. User stories & acceptance criteria

### Notebooks

**N1 — Create & list notebooks.** As a user I can create notebooks and see them as cards.
- AC: create via dialog; new notebook appears without reload; name 1–100 chars; empty state explains what to do.

**N2 — Rename & delete.** As a user I can rename inline and delete with confirmation.
- AC: rename persists; delete cascades (sources, files, vectors, messages) after confirm; deleted notebook disappears from list.

**N3 — Isolation.** As a user I get answers only from the notebook I'm in.
- AC: same question in two notebooks yields source-scoped answers; retrieval always filters by `notebook_id` (tested).

### Sources & ingestion

**S1 — Add plain text.** Paste text → becomes a source.
**S2 — Add PDF.** Upload a PDF → stored and indexed; original file viewable.
**S3 — Add website URL.** Paste a URL → page text extracted and indexed.
**S4 — Add YouTube video.** Paste a video URL → transcript extracted with timestamps.
**S5 — Add VTT transcript.** Upload a `.vtt` file → cues parsed with timestamps.
**S6 — Lifecycle visibility.** Every source shows `queued → processing(stage) → ready | failed`.
**S7 — Remove source.** Deleting a source also removes its vectors; answers stop citing it.
**S8 — Re-index.** Re-indexing re-runs extraction/chunking/embedding without duplicating vectors.

AC (shared): statuses update in the UI within ~2s while active; failures show a readable error and can be retried; app restart mid-ingest recovers (`processing` → `queued`); each ready source reports chunk count; duplicate adds are warned.

### Querying & answers

**Q1 — Ask a question.** Natural-language question about the notebook's content.
- AC: answer streams token-by-token; grounded in retrieved chunks; says it can't find the answer if the notebook lacks it.

**Q2 — See sources used.** Every claim is attributable.
- AC: `[n]` markers in the answer; the response carries the exact chunk mapping used (snapshot), not a re-query at click time.

**Q3 — History.** Conversation survives reload.
- AC: messages (user + assistant, with citations) reload in order in the same notebook.

### Citations & viewer

**C1 — Click citation → correct moment.**
- AC per type: PDF opens at the cited page (+ snippet); website opens stored page text with the passage highlighted; YouTube seeks to the cited timestamp; plain text and VTT highlight the cited chunk.

**C2 — Metadata preserved.**
- AC: citation payload includes title, type, and location (`page`, `start_seconds`, `url`, or offsets) wherever the format provides it.

**C3 — Clear citation UX.**
- AC: citation chips are visible inline, numbered, and listing the used sources is always one glance away.

### Bonus (⭐ Phase 8 only)

**B1 — YouTube playlist → personalized learning roadmap.** Ingest a playlist; produce an ordered study plan with links to the right timestamps.
**B2 — Podcast-style voice-over.** Generate an audio summary of selected sources with an inline player.

## 5. Functional requirements (summary)

- Web app (Next.js) + API (FastAPI) + Postgres/pgvector; no external queue or search service.
- Multipart upload for PDF/VTT; JSON for text/URL/YouTube; upload cap `MAX_UPLOAD_MB` (default 20 MB, PDFs only).
- One default conversation per notebook (extensible later).
- Chat model is provider-switchable via env: OpenAI or DeepSeek.
- All five extractors must fail gracefully (bad URL, transcripts disabled, malformed VTT) with a `failed` status + message.

## 6. Non-functional requirements

- **Performance**: warm first token < ~3 s; typical source indexed < 60 s; UI poll ≤ 2 s cadence.
- **Reliability**: ingestion state is durable (DB), crash-recoverable; idempotent re-index (no orphan/duplicate vectors).
- **Cost control**: `text-embedding-3-small`; chat on small/cheap models by default; batch embeddings; caps on file size and context size.
- **Observability**: structured logs with `source_id`, stage, duration; errors recorded on the source row.
- **Maintainability**: layered code (routers → services → data), typed schemas, tests per slice, migrations, ADRs.
- **Security/privacy**: no auth by design; secrets only in env; CORS allowlist; retrieved text treated as data (prompt-injection aware).

## 7. Success metrics (rubric mapping)

Full mapping lives in [CLAUDE.md §2](../CLAUDE.md). Condensed:

| Evidence | Rubric items |
|---|---|
| Notebook CRUD + isolation demo | 1 |
| All 5 source types + statuses + remove/re-index | 2 |
| Chunking/embedding/vector search + eval numbers | 3, 10 |
| Streamed grounded answers, refusals working | 4 |
| Citation deep-links for every source type | 5 |
| Clean layering, tests, migrations, ADRs | 6 |
| States, responsive, smooth interactions | 7 |
| README + docs | 8 |
| Demo video | 9 |

Killer demo flows that must work for the video: see [CLAUDE.md §3.3](../CLAUDE.md).

## 8. Milestones

| Milestone | Meaning | Target |
|---|---|---|
| P0–P1 | Foundation + notebooks working | early Nov 2026 |
| P2 | All sources ingest to `ready` | mid Nov 2026 |
| P3 | Full ask→stream→cite loop (demo-safe) | end Nov 2026 |
| P4–P5 | Retrieval depth + polish | first half Dec 2026 |
| P6–P7 | Deployed, README, demo video, submitted | mid Dec 2026 (buffer to 1 Jan 2027) |
| P8 ⭐ | Bonus only after submission-ready | late Dec 2026+ |

## 9. Open questions

1. Final default OpenAI chat model — confirm current small model at P3.2 (env-configurable, so low risk).
2. PDF highlight fidelity: page-jump + snippet side panel (MVP) vs attempt text-layer highlighting (P4.3) — decide after a spike.
3. Render tier: free (cold starts) vs paid for the demo window — decide at P6.1.

## 10. Out of scope (revisited)

Everything in §3's non-goals. When asked about them in evaluation: the assignment grades RAG depth and grounding; those features were consciously excluded to keep the data model and UX focused.
