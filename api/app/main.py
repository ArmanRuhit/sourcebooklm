"""SourcebookLM API - app factory and entry point."""

from fastapi import FastAPI

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(title="SourcebookLM API", version="0.1.0")

    @app.get(f"{API_PREFIX}/health", summary="Liveness check")
    async def health() -> dict[str, str]:
        """Return ok when the API process is up."""
        return {"status": "ok"}

    return app


app = create_app()
