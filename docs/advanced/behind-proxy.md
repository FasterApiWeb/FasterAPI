# Behind a Proxy

When FasterAPI runs behind a reverse proxy (Nginx, Traefik, AWS ALB, …), the
original client IP and URL scheme may be rewritten.  Configure your app to trust
forwarded headers.

## The problem

Without configuration, `request.client` returns the **proxy's IP**, not the browser's.
Similarly, `request.url.scheme` may say `http` even though the client used `https`.

## Trusting `X-Forwarded-For`

```python
from FasterAPI import Faster, Request

app = Faster()


@app.get("/ip")
async def client_ip(request: Request):
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # X-Forwarded-For can be a comma-separated list: client, proxy1, proxy2
        real_ip = forwarded_for.split(",")[0].strip()
    else:
        real_ip = request.client[0] if request.client else None
    return {"ip": real_ip}
```

!!! warning
    Only trust `X-Forwarded-For` if your app is **guaranteed to be behind a proxy**
    that strips or overwrites this header. Otherwise a client can spoof it.

## Root path

If your API is mounted at a sub-path (e.g. `/api/v1`), tell the server via the
`root_path` ASGI extension.  Pass it to uvicorn:

```bash
uvicorn main:app --root-path /api/v1
```

Or set in a middleware:

```python
from FasterAPI import BaseHTTPMiddleware


class RootPathMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, root_path: str = ""):
        super().__init__(app)
        self.root_path = root_path

    async def dispatch(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            scope = {**scope, "root_path": self.root_path}
        await self.app(scope, receive, send)


app.add_middleware(RootPathMiddleware, root_path="/api/v1")
```

This makes Swagger UI generate correct server URLs.

## Nginx configuration

```nginx
upstream fasterapi {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate     /etc/ssl/certs/api.pem;
    ssl_certificate_key /etc/ssl/private/api.key;

    location /api/ {
        proxy_pass         http://fasterapi/;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_redirect     off;
    }
}
```

## Traefik configuration (Docker labels)

```yaml
services:
  api:
    image: my-fasterapi-app
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=PathPrefix(`/api`)"
      - "traefik.http.routers.api.entrypoints=websecure"
      - "traefik.http.middlewares.strip-api.stripprefix.prefixes=/api"
      - "traefik.http.routers.api.middlewares=strip-api"
```

## Trusted host validation

Only allow requests with specific `Host` headers to prevent host-header injection:

```python
from FasterAPI import TrustedHostMiddleware

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["api.example.com", "*.example.com"],
)
```

## HTTPS redirect

Redirect all plain HTTP traffic to HTTPS at the application layer (usually handled
by the proxy, but useful as a safety net):

```python
from FasterAPI import HTTPSRedirectMiddleware

app.add_middleware(HTTPSRedirectMiddleware)
```

## Next steps

- [Deployment: Nginx/Traefik](../deployment/nginx-traefik.md) — full proxy configs.
- [Deployment: Docker](../deployment/docker.md) — containerised deployments.
