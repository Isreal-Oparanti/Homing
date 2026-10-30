"""FastAPI app factory. Slow work never runs here; it goes to the worker.

See docs/01-architecture.md.
"""

from fastapi import FastAPI

from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="Homing API",
        docs_url="/docs" if settings.is_local else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_local else None,
    )
    register_error_handlers(app)
    app.include_router(v1_router)
    return app


app = create_app()
