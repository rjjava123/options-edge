"""FastAPI dependency injection functions."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.config import get_settings as _get_settings
from app.data.polygon_client import PolygonClient
from app.db.database import get_db as _get_db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session.

    Re-exports :func:`app.db.database.get_db` so routes import from a
    single ``deps`` module.
    """
    async for session in _get_db():
        yield session


def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return _get_settings()


def get_polygon_client() -> PolygonClient:
    """Return a fresh :class:`PolygonClient` configured from settings.

    The caller is responsible for closing the client (or using it as an
    async context manager).
    """
    settings = _get_settings()
    return PolygonClient(api_key=settings.POLYGON_API_KEY)
