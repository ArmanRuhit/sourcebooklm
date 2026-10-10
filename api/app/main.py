"""SourcebookLM API - app factory and entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

API_PREFIX = "/api/v1"

# Web dev server origin allowed by CORS; TODO(P1): move to settings.
WEB_ORIGIN = "http://localhost:3000"


def create_app() -> FastAPI:
    app = FastAPI(title="SourcebookLM API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[WEB_ORIGIN],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get(f"{API_PREFIX}/health", summary="Liveness check")
    async def health() -> dict[str, str]:
        """Return ok when the API process is up."""
        return {"status": "ok"}

    return app


app = create_app()
