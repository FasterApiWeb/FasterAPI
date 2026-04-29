"""Structured logging helpers (optional ``structlog`` dependency)."""

from __future__ import annotations

import logging as logging_module
from typing import Any

try:
    import structlog as structlog_module
except ImportError:  # pragma: no cover
    structlog_module = None


def configure_structlog(
    *,
    json_format: bool = False,
    log_level: str = "INFO",
) -> Any:
    """Configure ``structlog`` for JSON or console output.

    Requires ``pip install structlog``. Safe to call once at process startup.

    Bind fields per request (often ``request_id`` from middleware) via::

        import structlog
        structlog.contextvars.bind_contextvars(request_id=...)
    """
    if structlog_module is None:
        raise ImportError("structlog is not installed. Install with: pip install structlog")

    lvl = getattr(logging_module, log_level.upper(), logging_module.INFO)
    if not isinstance(lvl, int):
        lvl = logging_module.INFO

    processors: list[Any] = [
        structlog_module.contextvars.merge_contextvars,
        structlog_module.processors.add_log_level,
        structlog_module.processors.StackInfoRenderer(),
        structlog_module.processors.format_exc_info,
    ]
    if json_format:
        processors.append(structlog_module.processors.TimeStamper(fmt="iso", utc=True))
        processors.append(structlog_module.processors.JSONRenderer())
    else:
        processors.append(structlog_module.dev.ConsoleRenderer())

    structlog_module.configure(
        processors=processors,
        wrapper_class=structlog_module.make_filtering_bound_logger(lvl),
        context_class=dict,
        logger_factory=structlog_module.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog_module
