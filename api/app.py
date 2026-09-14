"""FastAPI application: the HTTP face of botcore."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config import ApiSettings, load_api_settings
from api.container import ApiContainer
from api.routes import auth, raffles

API_TITLE = "botcore API"
API_VERSION = "0.1.0"
API_DESCRIPTION = (
    "Admin API over the database shared with the Telegram bot. "
    "The API writes raffles, the bot announces them and runs the draw at the deadline."
)


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build the application. Raises ApiConfigError when API_JWT_SECRET is missing."""
    container = ApiContainer.create(settings or load_api_settings(os.environ))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await container.init()
        try:
            yield
        finally:
            await container.close()

    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.container = container
    app.include_router(auth.router)
    app.include_router(raffles.router)

    @app.get("/health", tags=["service"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
