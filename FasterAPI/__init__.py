"""FasterAPI — A high-performance ASGI web framework.

Drop-in FastAPI replacement powered by msgspec (C extension JSON),
radix-tree routing, uvloop, and Python 3.13 sub-interpreters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._version import get_version

__version__ = get_version()
__author__ = "Eshwar Chandra Vidhyasagar Thedla"

from .app import Faster
from .asgi_compat import get_header, get_server_host, http_version, is_http2
from .background import BackgroundTask, BackgroundTasks
from .concurrency import SubInterpreterPool, run_in_subinterpreter
from .datastructures import FormData, UploadFile
from .dependencies import Depends
from .exceptions import HTTPException, RequestValidationError
from .log_config import configure_structlog
from .middleware import (
    BaseHTTPMiddleware,
    CORSMiddleware,
    GZipMiddleware,
    HTTPSRedirectMiddleware,
    TrustedHostMiddleware,
)
from .params import Body, Cookie, File, Form, Header, Path, Query
from .production import DatabasePoolMiddleware, RateLimitMiddleware, RequestIDMiddleware
from .request import Request
from .response import (
    EventSourceResponse,
    FileResponse,
    HTMLResponse,
    JSONResponse,
    ORJSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
    UJSONResponse,
)
from .router import FasterRouter, RadixRouter
from .security import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    HTTPBasic,
    HTTPBasicCredentials,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
    SecurityScopes,
)
from .staticfiles import StaticFiles
from .templating import Jinja2Templates
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
    "ORJSONResponse",
    "UJSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "RedirectResponse",
    "StreamingResponse",
    "FileResponse",
    "EventSourceResponse",
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
    # Production (v0.2)
    "DatabasePoolMiddleware",
    "RateLimitMiddleware",
    "RequestIDMiddleware",
    "configure_structlog",
    "http_version",
    "is_http2",
    "get_server_host",
    "get_header",
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
    # Security
    "SecurityScopes",
    "OAuth2PasswordBearer",
    "OAuth2PasswordRequestForm",
    "HTTPBasic",
    "HTTPBasicCredentials",
    "APIKeyHeader",
    "APIKeyQuery",
    "APIKeyCookie",
    # Static files & Templates
    "StaticFiles",
    "Jinja2Templates",
    # Testing
    "TestClient",
]


def __getattr__(name: str) -> Any:
    if name == "TestClient":
        try:
            from .testclient import TestClient as _TestClient
        except ModuleNotFoundError as e:
            if getattr(e, "name", None) == "httpx":
                raise ImportError("TestClient requires httpx. Install with: pip install httpx") from e
            raise
        return _TestClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
