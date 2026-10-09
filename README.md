# SourcebookLM

An AI research assistant in the spirit of Gemini Notebook: create notebooks, add sources — PDF, plain text, website URL, YouTube video, or VTT transcript — and ask questions answered **only** from those sources, with citations that deep-link back into the original material.

> **Status:** early build 🚧 — this README is a placeholder. The full version (setup, architecture, retrieval flow, env vars) ships with the first deployment.

## Project docs

| Doc | What it covers |
|---|---|
| [`docs/prd.md`](docs/prd.md) | What & why: users, stories, non-goals |
| [`docs/technical-design.md`](docs/technical-design.md) | How: architecture, data model, API, ingestion + retrieval design |
| [`docs/tasks.md`](docs/tasks.md) | Slice-by-slice build plan with acceptance criteria |

## Planned stack

- **API** — FastAPI (Python 3.13) · LangChain 1.x + LangGraph · SQLAlchemy 2 async
- **Retrieval** — Postgres + pgvector, single `chunks` collection, every search filtered by notebook
- **Web** — Next.js 16 (App Router, TypeScript, Tailwind 4, shadcn/ui)
- **Deploy** — Vercel (web) · Render (api) · Neon (db)
