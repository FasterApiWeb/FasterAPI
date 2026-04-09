"""Shared typing aliases for ASGI callables."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# ASGI application / handler (scope, receive, send) or route endpoint
ASGIApp = Callable[..., Any]

__all__ = ["ASGIApp"]
