"""SourcebookLM API - app factory and entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import notebooks, query, sources
from app.services import vector_store
from app.services.ingestion import worker

API_PREFIX = "/api/v1"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Prepare the vector store, recover jobs, then run the worker."""
    try:
        await vector_store.ensure_vector_store()
    except vector_store.EmbeddingConfigError as exc:
        logger.warning("vector store unavailable: %s", exc)

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
    app.include_router(query.router, prefix=API_PREFIX)
    app.include_router(sources.notebook_sources_router, prefix=API_PREFIX)
    app.include_router(sources.sources_router, prefix=API_PREFIX)

    @app.get(f"{API_PREFIX}/health", summary="Liveness check")
    async def health() -> dict[str, str]:
        """Return ok when the API process is up."""
        return {"status": "ok"}

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        """Log unexpected failures with request context and never leak internals."""
        logger.exception(
            "Unhandled error on %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
