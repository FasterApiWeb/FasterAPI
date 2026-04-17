# Security

Security is an important — and often underestimated — part of API development.
This section covers authentication and authorisation patterns for FasterAPI.

## Pages

| Topic | What you learn |
|---|---|
| [OAuth2 with Password + JWT](oauth2-jwt.md) | Bearer tokens, login endpoint, protected routes |
| [OAuth2 Scopes](oauth2-scopes.md) | Fine-grained permission checks |
| [HTTP Basic Auth](http-basic-auth.md) | Simple username / password authentication |

## Core concepts

### Authentication vs authorisation

- **Authentication** — verifying *who* a user is (login, token validation).
- **Authorisation** — verifying *what* a user may do (role checks, scopes).

### Secrets and keys

- Store secrets in **environment variables**, never in code or version control.
- Use a cryptographically secure random value for `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### HTTPS

Always serve your API over **HTTPS** in production so credentials are not transmitted
in plain text.  See [Behind a Proxy](../advanced/behind-proxy.md) and
[Deployment](../deployment/index.md) for setup guidance.

### Dependency-based security

FasterAPI's `Depends()` system is well-suited for security: declare an auth
dependency once and reuse it across many routes.

```python
from FasterAPI import Depends, HTTPException, Header


async def require_auth(authorization: str | None = Header(default=None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # validate token here
    return parse_token(authorization)
```

## Next steps

- Start with [OAuth2 with Password + JWT](oauth2-jwt.md) for the most common pattern.
- For simple internal tools, [HTTP Basic Auth](http-basic-auth.md) may be sufficient.
