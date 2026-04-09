"""FasterAPI — A high-performance ASGI web framework.

Drop-in FastAPI replacement powered by msgspec (C extension JSON),
radix-tree routing, uvloop, and Python 3.13 sub-interpreters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._version import get_version

__version__ = get_version()

from .app import Faster
from .background import BackgroundTask, BackgroundTasks
from .concurrency import SubInterpreterPool, run_in_subinterpreter
from .datastructures import FormData, UploadFile
from .dependencies import Depends
from .exceptions import HTTPException, RequestValidationError
from .middleware import (
    BaseHTTPMiddleware,
    CORSMiddleware,
    GZipMiddleware,
    HTTPSRedirectMiddleware,
    TrustedHostMiddleware,
)
from .params import Body, Cookie, File, Form, Header, Path, Query
from .request import Request
from .response import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from .router import FasterRouter, RadixRouter
from .websocket import WebSocket, WebSocketDisconnect, WebSocketState

if TYPE_CHECKING:
    from .testclient import TestClient as TestClient

__all__ = [
    "__version__",
    # Core
    "Faster",
    "FasterRouter",
    "RadixRouter",
    "Request",
    # Responses
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "RedirectResponse",
    "StreamingResponse",
    "FileResponse",
    # Params
    "Body",
    "Cookie",
    "File",
    "Form",
    "Header",
    "Path",
    "Query",
    # DI
    "Depends",
    # Exceptions
    "HTTPException",
    "RequestValidationError",
    # Middleware
    "BaseHTTPMiddleware",
    "CORSMiddleware",
    "GZipMiddleware",
    "HTTPSRedirectMiddleware",
    "TrustedHostMiddleware",
    # Background
    "BackgroundTask",
    "BackgroundTasks",
    # WebSocket
    "WebSocket",
    "WebSocketDisconnect",
    "WebSocketState",
    # Data structures
    "FormData",
    "UploadFile",
    # Concurrency
    "SubInterpreterPool",
    "run_in_subinterpreter",
    # Testing
    "TestClient",
]


def __getattr__(name: str):
    if name == "TestClient":
        try:
            from .testclient import TestClient as _TestClient
        except ModuleNotFoundError as e:
            if getattr(e, "name", None) == "httpx":
                raise ImportError(
                    "TestClient requires httpx. Install with: pip install httpx",
                ) from e
            raise
        return _TestClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
