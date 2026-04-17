# Middleware

Middleware wraps every request and response.  Use it for cross-cutting concerns:
CORS, compression, authentication headers, logging, rate-limiting.

## Adding built-in middleware

### CORS

```python
from FasterAPI import Faster, CORSMiddleware

app = Faster()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com", "https://app.example.com"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)
```

Allow all origins during development:

```python
app.add_middleware(CORSMiddleware, allow_origins=["*"])
```

### GZip compression

```python
from FasterAPI import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
```

Responses smaller than `minimum_size` bytes are sent uncompressed.

### HTTPS redirect

```python
from FasterAPI import HTTPSRedirectMiddleware

app.add_middleware(HTTPSRedirectMiddleware)
```

Redirects every HTTP request to its HTTPS equivalent (301).

### Trusted host

```python
from FasterAPI import TrustedHostMiddleware

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["example.com", "*.example.com"],
)
```

Requests with a `Host` header not in the list receive a 400 response.

## Custom middleware

Subclass `BaseHTTPMiddleware` and override `dispatch`:

```python
import time
from FasterAPI import Faster, BaseHTTPMiddleware, Request
from typing import Any

app = Faster()


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, scope, receive, send):
        start = time.perf_counter()

        captured: list[dict] = []

        async def capture_send(message: dict) -> None:
            captured.append(message)

        await self.app(scope, receive, capture_send)

        elapsed = time.perf_counter() - start
        for message in captured:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(
                    (b"x-process-time", f"{elapsed:.4f}".encode())
                )
                message = {**message, "headers": headers}
            await send(message)


app.add_middleware(TimingMiddleware)
```

## Middleware execution order

Middleware is applied in **reverse registration order** — the last added wraps
outermost. For example:

```python
app.add_middleware(CORSMiddleware, ...)    # runs second (outer)
app.add_middleware(GZipMiddleware, ...)    # runs first (inner)
```

## Accessing request information in middleware

```python
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, scope, receive, send):
        method = scope.get("method", "")
        path = scope.get("path", "")
        print(f"→ {method} {path}")
        await self.app(scope, receive, send)
```

## Next steps

- [WebSockets](websockets.md) — real-time bidirectional communication.
- [Metadata & Docs](metadata.md) — customise the OpenAPI UI.
