"""FastAPI app factory. Slow work never runs here; it goes to the worker.

See docs/01-architecture.md.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Locally, the worker runs inside the API process (RUN_WORKER_IN_API=true)."""
    runner = None
    if get_settings().run_worker_in_api:
        from app.worker import build_runner

        runner = build_runner()
        runner.start()
    yield
    if runner is not None:
        runner.stop()


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="Homing API",
        docs_url="/docs" if settings.is_local else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_local else None,
        lifespan=lifespan,
    )
    # Browsers send files straight here with an upload ticket. The API never reads cookies,
    # so letting any page call it gives nothing away: every route still needs the proxy
    # secret or a signed ticket.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["POST"],
        allow_headers=["Authorization"],
    )
    register_error_handlers(app)
    app.include_router(v1_router)
    return app


app = create_app()
