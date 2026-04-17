# Response Cookies & Headers

## Setting response headers

Pass a `headers` dict to any response class:

```python
from FasterAPI import Faster, JSONResponse

app = Faster()


@app.get("/items")
async def list_items():
    return JSONResponse(
        {"items": []},
        headers={
            "X-Total-Count": "0",
            "Cache-Control": "public, max-age=60",
            "X-Request-ID": "abc-123",
        },
    )
```

### Security headers

```python
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


@app.get("/secure")
async def secure_endpoint():
    return JSONResponse({"ok": True}, headers=SECURITY_HEADERS)
```

### Headers via middleware

Apply headers to every response without touching individual routes:

```python
from FasterAPI import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, scope, receive, send):
        async def add_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for k, v in SECURITY_HEADERS.items():
                    headers.append((k.lower().encode(), v.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, add_headers)


app.add_middleware(SecurityHeadersMiddleware)
```

## Setting cookies

Use a `Response` subclass and call helpers on the underlying response object, or
construct the `Set-Cookie` header manually:

```python
from FasterAPI import Response


@app.post("/login")
async def login(response: Response):
    # FasterAPI injects Response when declared as parameter type
    # Use headers dict for cookie setting
    return JSONResponse(
        {"logged_in": True},
        headers={
            "Set-Cookie": (
                "session=abc123; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=3600"
            )
        },
    )
```

### Structured cookie header builder

```python
def make_cookie(
    name: str,
    value: str,
    *,
    max_age: int | None = None,
    path: str = "/",
    secure: bool = True,
    http_only: bool = True,
    same_site: str = "Strict",
) -> str:
    parts = [f"{name}={value}", f"Path={path}"]
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    if secure:
        parts.append("Secure")
    if http_only:
        parts.append("HttpOnly")
    parts.append(f"SameSite={same_site}")
    return "; ".join(parts)


@app.post("/auth")
async def auth():
    cookie = make_cookie("token", "jwt-here", max_age=3600)
    return JSONResponse({"ok": True}, headers={"Set-Cookie": cookie})
```

### Deleting a cookie

Set `Max-Age=0`:

```python
@app.post("/logout")
async def logout():
    return JSONResponse(
        {"logged_out": True},
        headers={"Set-Cookie": "session=; Max-Age=0; Path=/; HttpOnly; Secure"},
    )
```

## Reading cookies in a request

```python
from FasterAPI import Cookie


@app.get("/profile")
async def profile(session: str | None = Cookie(default=None)):
    if session is None:
        return {"authenticated": False}
    return {"session": session}
```

## Next steps

- [Custom Response Classes](custom-response.md) — full response control.
- [Security: HTTP Basic Auth](../security/http-basic-auth.md) — cookie-based auth patterns.
