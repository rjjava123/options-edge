"""CRUD operations for screener_configs table."""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thesis import ScreenerConfig


async def create_screener_config(session: AsyncSession, **kwargs) -> ScreenerConfig:
    config = ScreenerConfig(**kwargs)
    session.add(config)
    await session.flush()
    return config


async def get_screener_config(
    session: AsyncSession, config_id: uuid.UUID
) -> Optional[ScreenerConfig]:
    return await session.get(ScreenerConfig, config_id)


async def list_screener_configs(
    session: AsyncSession, *, active_only: bool = False
) -> Sequence[ScreenerConfig]:
    stmt = select(ScreenerConfig).order_by(ScreenerConfig.name)
    if active_only:
        stmt = stmt.where(ScreenerConfig.is_active == True)  # noqa: E712
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_screener_config(
    session: AsyncSession, config_id: uuid.UUID, **kwargs
) -> Optional[ScreenerConfig]:
    config = await session.get(ScreenerConfig, config_id)
    if config is None:
        return None
    for key, value in kwargs.items():
        setattr(config, key, value)
    await session.flush()
    return config


async def delete_screener_config(
    session: AsyncSession, config_id: uuid.UUID
) -> bool:
    config = await session.get(ScreenerConfig, config_id)
    if config is None:
        return False
    await session.delete(config)
    await session.flush()
    return True
