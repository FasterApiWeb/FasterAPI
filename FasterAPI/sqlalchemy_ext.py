"""SQLAlchemy 2.0 async session dependency helpers (optional ``sqlalchemy`` extra)."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Any

__all__ = ["sqlalchemy_session_dependency", "async_engine_from_url_optional"]


def sqlalchemy_session_dependency(session_factory: Any) -> Callable[..., AsyncGenerator[Any, None]]:
    """Return an async dependency that yields one :class:`sqlalchemy.ext.asyncio.AsyncSession`.

    The factory must be an :class:`async_sessionmaker` (or any callable returning
    an object usable as ``async with session_factory() as session:``.

    Usage::

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from FasterAPI import Depends, Faster
        from FasterAPI.sqlalchemy_ext import sqlalchemy_session_dependency

        engine = create_async_engine(\"postgresql+asyncpg://...\", echo=False)
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
        get_session = sqlalchemy_session_dependency(SessionLocal)

        app = Faster()

        @app.get(\"/rows\")
        async def rows(session: AsyncSession = Depends(get_session)):
            ...

    Install: ``pip install faster-api-web[ecosystem]`` or ``sqlalchemy[asyncio]``.
    """
    if session_factory is None:
        raise ValueError("session_factory is required")

    async def get_session() -> AsyncGenerator[Any, None]:
        async with session_factory() as session:
            yield session

    return get_session


def async_engine_from_url_optional(url: str, **kwargs: Any) -> Any:
    """Create an async engine if SQLAlchemy is installed; raise ``ImportError`` otherwise."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError as exc:
        raise ImportError(
            "SQLAlchemy is required. Install with: pip install 'sqlalchemy[asyncio]'",
        ) from exc
    return create_async_engine(url, **kwargs)
