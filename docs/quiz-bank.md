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
