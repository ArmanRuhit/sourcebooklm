# Quiz bank — deferred review questions

**Why this file exists:** owner directive (2026-10-10) — in a time crunch, the per-slice quiz step (CLAUDE.md §7.1) is deferred. The agent banks the 3 questions per slice (fundamental / tradeoff / failure-mode) here; we answer them in review sessions **after the full build** — or on demand (say "quiz me").

**How to use at review time:** answer in your own words; anything you can't explain, we re-read that slice and redo it. These questions double as interview-prep material.

## P0.2 — API scaffold (banked 2026-10-10 · answered once, 2 gaps to revisit)

1. **Fundamental** — `main.py` defines `create_app()` and then `app = create_app()`. Why the factory instead of `app = FastAPI(...)` directly? Name one concrete thing it enables later.
2. **Tradeoff** — `pyproject.toml` pins `==` versions *and* `uv.lock` freezes 96 packages. What does each file guarantee? What's the cost of exact pins vs `>=x,<y` ranges (e.g., how does a security fix reach us)?
3. **Failure mode** — The health test calls the app in-process (`ASGITransport`) and never starts a server. Name one real bug that would pass this test but break the real uvicorn server.

*(P0.1 quiz was completed under the old workflow — no backlog.)*

## P0.4 — web scaffold + CORS (banked 2026-10-10)

1. **Fundamental** — Before the CORS patch, the browser page couldn't read `/api/v1/health` (it showed "Failed to fetch") while `curl` got a 200 from the same URL at the same time. Who enforces CORS, and what exactly did the middleware change about the API's *responses*?
2. **Tradeoff** — `allow_origins=[WEB_ORIGIN]` allows exactly one origin vs `allow_origins=["*"]`. What does the wildcard buy you, and what must change once the app uses cookies/auth (why can't `*` and `allow_credentials=true` coexist)? Why did we deliberately skip `allow_credentials` for now?
3. **Failure mode** — After deploying (Vercel web + Render api), someone forgets to point `WEB_ORIGIN` at the real web URL. The health card says "Unreachable: Failed to fetch" while the API uptime check is green. Explain why that symptom points at CORS, not at the API being down.

## P1.1 — schema + migrations (banked 2026-10-26)

1. **Fundamental** — Alembic's `env.py` sets `target_metadata = Base.metadata`. What exactly does `--autogenerate` compare, and what happens if someone edits a column in `models.py` but ships no new migration?
2. **Tradeoff** — Why does Alembic keep an `alembic_version` table and a chain of revisions instead of just running idempotent `CREATE TABLE IF NOT EXISTS` scripts at startup? What does the chain buy you on downgrade?
3. **Failure mode** — A deploy ships the new API but `alembic upgrade head` never ran against the production DB (or a migration dies halfway). What breaks first, and why does PostgreSQL's transactional DDL make the halfway case safe?

## P1.2 — notebooks CRUD API (banked 2026-10-28)

1. **Fundamental** — `NotebookName` uses `StringConstraints(strip_whitespace=True, min_length=1, max_length=100)`. For `{"name": "   "}`, where is it rejected, and why does strip-before-min_length turn a whitespace-only name into a 422 instead of an empty-named notebook?
2. **Tradeoff** — Services return ORM `Notebook` objects and the router declares `response_model=NotebookRead` with `from_attributes=True`. What does that shortcut cost you (what does the router now depend on), and why does `from_attributes` keep the door open to return dicts/dataclasses later?
3. **Failure mode** — `test_delete_notebook_cascades` only passes because of the DB-level `ON DELETE CASCADE` on `sources.notebook_id`. If that clause were dropped, what would the API's DELETE return instead of 204 — and why would an orphan-row outcome be worse than an error?

## P1.3 — notebooks UI (banked 2026-10-28)

1. **Fundamental** — `request<T>` returns `undefined as T` for a 204 and otherwise casts `response.json()`. Where does the type system stop protecting you, and what would a `deleteNotebook` caller see if the API started returning `200 {"deleted": true}` instead of 204?
2. **Tradeoff** — Create/rename dialogs are mounted only while open, so each open starts from fresh `useState`. What does that pattern buy over keeping them mounted + resetting fields in an effect, and what does it cost (think exit animation, in-progress form state, focus)?
3. **Failure mode** — The first typed client had `` fetch(`{API_URL}${path}`) `` (missing `$`) and `Content-Type: application/json` on GETs. Trace what the browser actually requests and why the failure surfaces as a `Request failed` toast instead of CORS/network noise.

## P1.4 — notebook workspace shell (banked 2026-10-28)

1. **Fundamental** — A request to `/notebooks/not-a-real-id` returns 422, not 404, because FastAPI validates the `UUID` path param before the handler runs. Why does the page map both 404 and 422 to "missing", and what does that say about the only input this route accepts?
2. **Tradeoff** — The page fetches in a client effect and renders its own missing state, instead of being a server component that calls `getNotebook()` and `notFound()`. What do you gain (loading/retry UX, no server-side API origin coupling, simple client cache behavior) and what do you lose (real 404 HTTP status, server-rendered notebook name, one extra round trip after hydration)?
3. **Failure mode** — The fetch effect depends on `[id, reloadKey]`. If someone removes `id` from the dependency array, what happens when the user navigates from notebook A to notebook B through a client-side link, and why would the URL and the displayed name disagree?

## P2.1 — source API + worker skeleton (banked 2026-10-28)

1. **Fundamental** — `claim_next` selects a row `FOR UPDATE SKIP LOCKED`, flips it to `processing`, and commits before the pipeline runs. Why release the lock immediately instead of holding it for the whole job, and what makes the claim safe without that lock?
2. **Tradeoff** — The `sources` table is the queue: no Redis, no Celery. What does that buy (one datastore, transactional status changes, simple deploy) and what does it cost at higher scale (polling, idle connections, no retry/priority features, worker count limits)?
3. **Failure mode** — A worker dies after committing `status='processing'` but before finishing. Trace the recovery: what does `requeue_stale` change, why is that safe to run at every startup, and what would happen to the source if no startup requeue existed?

## P2.2 — text pipeline (banked 2026-10-28)

1. **Fundamental** — Chunks use 1000 chars with 150 chars of overlap and keep `char_start`/`char_end`. What does the overlap protect against at retrieval time, and what would citations lose if the offsets were dropped?
2. **Tradeoff** — Re-indexing deletes a source's vectors and re-adds them with deterministic `source_id:index` IDs. What does that buy (idempotency, no stale chunks) and what does it cost compared with upserting only changed chunks (embedding spend, a brief window with no vectors)?
3. **Failure mode** — `langchain-postgres 0.0.19`'s `adelete(filter={...})` accepts a filter and silently deletes nothing. What would you observe after deleting or re-indexing a source, and how do you make the operation trustworthy? (The fix deletes by `cmetadata->>'source_id'` in SQL.)

## P2.3 — PDF ingestion + viewer (banked 2026-10-28)

1. **Fundamental** — `split_pages` chunks each page separately and keeps `char_start`/`char_end` relative to that page. Why is page-relative better than one global character offset for citations, and what breaks if chunk text is allowed to overlap across a page boundary?
2. **Tradeoff** — PDF bytes live in Postgres (`source_files.bytea`) instead of S3 or the filesystem. What does that buy for a small single-service app (transactional delete, one backup, simple local dev) and what does it cost (database size, write amplification, memory pressure when streaming large files)?
3. **Failure mode** — `useSources` polls only while the current list has an active source. After the initial list settles, a newly uploaded source is added locally as `queued` — why did polling never restart, and what is the minimal fix? (Here, `addSource` bumps the effect's `reloadKey`.)

## P2.4 — website URL ingestion (banked 2026-10-28)

1. **Fundamental** — Before fetching a user-supplied URL, `validate_public_url` resolves the hostname and rejects non-global IPs. What attack does that block, and why is checking the hostname string alone insufficient? What gap remains with HTTP redirects?
2. **Tradeoff** — The worker stores the extracted article text in `source_contents` instead of re-fetching the page when the viewer opens. What does that buy (stable citations, no network at view time, works after the page changes) and what does it cost (storage, staleness, no live refresh)?
3. **Failure mode** — Unit tests mocked `fetch_article`, so they passed while the production dependency `bs4` was missing. Why did only live smoke catch it, what kind of test covers the real loader, and when is mocking the whole extractor the wrong boundary?

## P2.5 — YouTube transcripts (banked 2026-10-28)

1. **Fundamental** — `split_transcript` never splits inside a cue and overlaps one cue between chunks. Why does that preserve citation quality, and what do `start_seconds`/`end_seconds` mean for a chunk that spans several cues?
2. **Tradeoff** — The viewer embeds YouTube's player instead of storing or transcoding the video. What does that avoid (bandwidth, storage, licensing) and what does it give up (offline playback, control over availability, embed restrictions)?
3. **Failure mode** — The oEmbed title lookup is best-effort while the transcript fetch is fatal. Why is that split correct, and what would users see if a title failure were treated like a transcript failure?

## P2.6 — VTT transcripts (banked 2026-10-28)

1. **Fundamental** — Why parse WebVTT into `(text, start, end)` cues instead of flattening the file to plain text and reusing the text chunker? Which later features become impossible if the timestamps are dropped?
2. **Tradeoff** — The app stores both the original `.vtt` bytes in `source_files` and the derived `segments`/chunks. What does keeping the original buy for the viewer and re-indexing, and what does it cost in storage and write complexity?
3. **Failure mode** — A file starts with `WEBVTT` but contains `00:00:02.000 --> 00:00:01.000`. The parser rejects it. Why not silently swap the endpoints, and where does the user see the consequence?

## P2.7 — delete, re-index, retry (banked 2026-10-28)

1. **Fundamental** — Re-index deletes the source's vectors before setting it `queued`, and the indexing step deletes again before adding. What invariant does that establish, and why is the second delete necessary for repeated or concurrent runs?
2. **Tradeoff** — Delete is a hard delete: rows cascade and vectors are removed immediately, with no soft-delete or undo. What does that simplify (queries never filter tombstones, storage is reclaimed) and what does it cost (accidental loss, no audit trail)?
3. **Failure mode** — The re-index endpoint returns 409 while a source is `processing` instead of queueing another run. What could happen if it accepted the request, and how does the `FOR UPDATE SKIP LOCKED` claim interact with that guard?

## P3 — grounded streaming chat (banked 2026-10-28)

1. **Fundamental** — Why does the SSE stream send `meta` and `citations` before any `token`, and why persist the user message before calling the LLM? What client and server behaviors does that ordering make possible when the connection drops mid-answer?
2. **Tradeoff** — Retrieval fetches 12 candidates but MMR returns only 6 to the prompt. Why not pass the top 6 by similarity? What does diversity buy for multi-part questions, and what does it cost in prompt size and relevance?
3. **Failure mode** — The model writes `[1]`, but citation metadata is produced by the app. Why must the app resolve `n` against the pre-built citation array instead of trusting any source ID the model might emit, and what would break if that array were reordered after generation?

## P4 — retrieval quality (banked 2026-10-28)

1. **Fundamental** — The eval harness measures hit@1/3/6 and MRR over 15 pairs. Why record all four instead of one accuracy number, and what does MRR capture that hit@3 hides?
2. **Tradeoff** — Reranking adds one LLM call before generation but raised fixture hit@1 from 0.93 to 1.00. When is that latency/cost worth it, and how should the app behave if the reranker times out?
3. **Failure mode** — PDF highlighting searches the rendered text layer for a compacted 40-character prefix of the snippet. What happens when extraction changes spacing or hyphenation, and why is falling back to the snippet banner safer than wrapping arbitrary DOM spans?

## P5 — UX & hardening (banked 2026-10-28)

1. **Fundamental** — Duplicate detection compares URL, or filename plus byte size, client-side. Why is this a warning rather than a hard block, and why can the client not be the final authority?
2. **Tradeoff** — On mobile the sources panel moves into a drawer instead of staying stacked above chat. What does the drawer buy in screen real estate, and what does it cost in discoverability and extra open/close state?
3. **Failure mode** — The FastAPI catch-all handler logs the exception and returns a generic detail string. Why not return `str(exc)` to the client, and what would an attacker learn from stack traces or SQL errors?
