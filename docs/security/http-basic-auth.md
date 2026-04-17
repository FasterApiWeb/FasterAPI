# HTTP Basic Authentication

HTTP Basic Auth sends a `username:password` pair encoded in Base64 with every
request.  It is the simplest authentication scheme — suitable for internal tools,
admin panels, or services protected by TLS where token management would be overkill.

!!! warning
    **Always use HTTPS** with Basic Auth.  The credentials are only Base64-encoded, not
    encrypted, so they are readable in plain text over HTTP.

## How it works

The client sends:

```
Authorization: Basic <base64(username:password)>
```

The server decodes and validates the credentials.  If invalid, it responds with:

```
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Protected"
```

## Implementation

```python
import base64
import secrets
from FasterAPI import Faster, Header, HTTPException

app = Faster()

# Store hashed passwords in production!
USERS = {
    "admin": "super-secret",
    "reader": "read-only-pass",
}


def decode_basic_auth(authorization: str | None) -> tuple[str, str] | None:
    if not authorization or not authorization.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(authorization.removeprefix("Basic ")).decode("utf-8")
        username, _, password = decoded.partition(":")
        return username, password
    except Exception:
        return None


async def require_basic_auth(
    authorization: str | None = Header(default=None),
) -> str:
    credentials = decode_basic_auth(authorization)
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": 'Basic realm="Protected Area"'},
        )

    username, password = credentials
    stored = USERS.get(username)

    # Use constant-time comparison to prevent timing attacks
    if stored is None or not secrets.compare_digest(password, stored):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="Protected Area"'},
        )

    return username
```

## Protecting routes

```python
from FasterAPI import Depends


@app.get("/admin", tags=["admin"])
async def admin_panel(user: str = Depends(require_basic_auth)):
    return {"logged_in_as": user}


@app.get("/reports", tags=["reports"])
async def reports(user: str = Depends(require_basic_auth)):
    return {"user": user, "reports": []}
```

## Testing

```bash
curl -u admin:super-secret http://localhost:8000/admin
# {"logged_in_as":"admin"}

curl http://localhost:8000/admin
# 401 Unauthorized
```

With Python requests:

```python
import httpx

r = httpx.get("http://localhost:8000/admin", auth=("admin", "super-secret"))
print(r.json())
```

## Hashing passwords

Do **not** store plain-text passwords.  Use bcrypt:

```bash
pip install passlib[bcrypt]
```

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"])

HASHED_USERS = {
    "admin": pwd_context.hash("super-secret"),
}


def verify(username: str, password: str) -> bool:
    hashed = HASHED_USERS.get(username)
    if hashed is None:
        return False
    return pwd_context.verify(password, hashed)
```

Update the dependency:

```python
async def require_basic_auth(authorization: str | None = Header(default=None)) -> str:
    creds = decode_basic_auth(authorization)
    if creds is None or not verify(*creds):
        raise HTTPException(
            401,
            headers={"WWW-Authenticate": 'Basic realm="Protected"'},
        )
    return creds[0]
```

## When to use Basic Auth

| Suitable | Not suitable |
|---|---|
| Internal admin panels over HTTPS | Public-facing APIs |
| Simple CLI tools | Apps requiring token refresh |
| Quick prototypes | Multi-tenant SaaS |

For public APIs, prefer [OAuth2 + JWT](oauth2-jwt.md).

## Next steps

- [OAuth2 with Password + JWT](oauth2-jwt.md) — stateless token authentication.
- [OAuth2 Scopes](oauth2-scopes.md) — fine-grained permissions.
