"""FasterAPI — A high-performance ASGI web framework."""

from .app import Faster
from .background import BackgroundTask, BackgroundTasks
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

__all__ = [
    "Faster",
    "BackgroundTask",
    "BackgroundTasks",
    "BaseHTTPMiddleware",
    "Body",
    "CORSMiddleware",
    "Cookie",
    "Depends",
    "FasterRouter",
    "File",
    "FileResponse",
    "Form",
    "FormData",
    "GZipMiddleware",
    "HTMLResponse",
    "HTTPException",
    "HTTPSRedirectMiddleware",
    "Header",
    "JSONResponse",
    "Path",
    "PlainTextResponse",
    "Query",
    "RadixRouter",
    "RedirectResponse",
    "Request",
    "RequestValidationError",
    "Response",
    "StreamingResponse",
    "TrustedHostMiddleware",
    "UploadFile",
    "WebSocket",
    "WebSocketDisconnect",
    "WebSocketState",
]
