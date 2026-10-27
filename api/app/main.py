"""SourcebookLM API - app factory and entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import notebooks, sources
from app.services.ingestion import worker

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Recover interrupted jobs, then run the ingestion worker with the app."""
    await worker.startup()
    task = asyncio.create_task(worker.run_worker(), name="ingestion-worker")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    app = FastAPI(title="SourcebookLM API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(notebooks.router, prefix=API_PREFIX)
    app.include_router(sources.notebook_sources_router, prefix=API_PREFIX)
    app.include_router(sources.sources_router, prefix=API_PREFIX)

    @app.get(f"{API_PREFIX}/health", summary="Liveness check")
    async def health() -> dict[str, str]:
        """Return ok when the API process is up."""
        return {"status": "ok"}

    return app


app = create_app()
