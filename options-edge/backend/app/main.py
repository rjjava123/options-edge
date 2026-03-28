"""FastAPI application entry point for Options Edge."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.database import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialise resources on startup, clean up on shutdown."""
    settings = get_settings()
    logging.basicConfig(level=settings.LOG_LEVEL)
    logger.info("Starting Options Edge API (env=%s)", settings.APP_ENV)

    # Create tables if they don't exist (dev convenience; use Alembic in prod)
    if not settings.is_production:
        await init_db()
        logger.info("Database tables initialised")

    yield

    logger.info("Shutting down Options Edge API")


app = FastAPI(
    title="Options Edge",
    description="AI-powered options trading thesis generation and tracking platform",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS (allow all origins for development)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from app.api.routes.discovery import router as discovery_router  # noqa: E402
from app.api.routes.validation import router as validation_router  # noqa: E402
from app.api.routes.watchlist import router as watchlist_router  # noqa: E402
from app.api.routes.theses import router as theses_router  # noqa: E402
from app.api.routes.active_trades import router as active_trades_router  # noqa: E402

app.include_router(discovery_router)
app.include_router(validation_router)
app.include_router(watchlist_router)
app.include_router(theses_router)
app.include_router(active_trades_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "options-edge"}
