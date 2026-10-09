# Quiz bank — deferred review questions

**Why this file exists:** owner directive (2026-10-10) — in a time crunch, the per-slice quiz step (CLAUDE.md §7.1) is deferred. The agent banks the 3 questions per slice (fundamental / tradeoff / failure-mode) here; we answer them in review sessions **after the full build** — or on demand (say "quiz me").

**How to use at review time:** answer in your own words; anything you can't explain, we re-read that slice and redo it. These questions double as interview-prep material.

## P0.2 — API scaffold (banked 2026-10-10 · answered once, 2 gaps to revisit)

1. **Fundamental** — `main.py` defines `create_app()` and then `app = create_app()`. Why the factory instead of `app = FastAPI(...)` directly? Name one concrete thing it enables later.
2. **Tradeoff** — `pyproject.toml` pins `==` versions *and* `uv.lock` freezes 96 packages. What does each file guarantee? What's the cost of exact pins vs `>=x,<y` ranges (e.g., how does a security fix reach us)?
3. **Failure mode** — The health test calls the app in-process (`ASGITransport`) and never starts a server. Name one real bug that would pass this test but break the real uvicorn server.

*(P0.1 quiz was completed under the old workflow — no backlog.)*
