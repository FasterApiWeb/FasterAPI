"""FasterAPI — A high-performance ASGI web framework.

Drop-in FastAPI replacement powered by msgspec (Rust-backed JSON),
radix-tree routing, uvloop, and Python 3.13 sub-interpreters.
"""

__version__ = "0.1.0"

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
from .testclient import TestClient
from .websocket import WebSocket, WebSocketDisconnect, WebSocketState

__all__ = [
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
