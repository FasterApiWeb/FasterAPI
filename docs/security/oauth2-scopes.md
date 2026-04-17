# OAuth2 Scopes

Scopes provide **fine-grained authorisation** — a token may grant access to only
a subset of operations (e.g. `read:items` but not `write:items`).

## Defining scopes

```python
# scopes.py
SCOPES = {
    "read:items":  "Read access to items",
    "write:items": "Create and update items",
    "delete:items":"Delete items",
    "admin":       "Full administrative access",
}
```

## Encoding scopes in the token

Add a `scopes` claim when creating the JWT:

```python
from auth import create_access_token
from datetime import timedelta

token = create_access_token(
    {"sub": "alice", "scopes": ["read:items", "write:items"]},
    expires_delta=timedelta(minutes=30),
)
```

## Security dependency with scope check

```python
from FasterAPI import Header, HTTPException, Depends
from auth import decode_access_token


def require_scope(*required_scopes: str):
    """Factory that returns a dependency checking for the given scopes."""

    async def _check(authorization: str | None = Header(default=None)):
        exc = HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
        if not authorization or not authorization.startswith("Bearer "):
            raise exc

        payload = decode_access_token(authorization.removeprefix("Bearer "))
        if payload is None:
            raise exc

        token_scopes: list[str] = payload.get("scopes", [])
        for scope in required_scopes:
            if scope not in token_scopes:
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient scope. Required: {scope}",
                    headers={"WWW-Authenticate": f'Bearer scope="{scope}"'},
                )
        return payload

    return _check
```

## Using scope dependencies in routes

```python
from FasterAPI import Faster, Depends
from scopes import require_scope

app = Faster()


@app.get("/items", tags=["items"])
async def list_items(_: dict = Depends(require_scope("read:items"))):
    return [{"name": "Widget"}]


@app.post("/items", status_code=201, tags=["items"])
async def create_item(_: dict = Depends(require_scope("write:items"))):
    return {"created": True}


@app.delete("/items/{item_id}", status_code=204, tags=["items"])
async def delete_item(item_id: int, _: dict = Depends(require_scope("delete:items"))):
    pass


@app.get("/admin", tags=["admin"])
async def admin_panel(_: dict = Depends(require_scope("admin"))):
    return {"panel": "admin"}
```

## Scoped login endpoint

Return different scopes based on the user's role:

```python
ROLE_SCOPES = {
    "user":  ["read:items"],
    "editor": ["read:items", "write:items"],
    "admin": ["read:items", "write:items", "delete:items", "admin"],
}

@app.post("/auth/token")
async def login(username: str = Form(), password: str = Form()):
    user = _fake_users_db.get(username)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(401, "Incorrect credentials")

    role = getattr(user, "role", "user")
    scopes = ROLE_SCOPES.get(role, [])

    token = create_access_token(
        {"sub": user.username, "scopes": scopes},
    )
    return {"access_token": token, "token_type": "bearer", "scopes": scopes}
```

## OAuth2 scope request (standard flow)

In a standard OAuth2 flow the client requests specific scopes at login time:

```bash
curl -X POST /auth/token \
  -d "username=alice&password=secret&scope=read:items write:items"
```

The server issues a token containing only the intersection of the requested scopes
and the user's allowed scopes.

## Next steps

- [OAuth2 with Password + JWT](oauth2-jwt.md) — the base authentication layer.
- [HTTP Basic Auth](http-basic-auth.md) — simpler alternative.
