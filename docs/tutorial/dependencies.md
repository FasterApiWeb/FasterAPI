# Dependencies

The `Depends()` system lets you declare **reusable, injectable logic** — authentication,
database sessions, pagination, etc. — that FasterAPI resolves before calling your
route handler.

## Basic dependency

Any callable (function or class) can be a dependency:

```python
from FasterAPI import Faster, Depends, Query

app = Faster()


async def common_pagination(skip: int = Query(default=0), limit: int = Query(default=10)):
    return {"skip": skip, "limit": limit}


@app.get("/items")
async def list_items(pagination: dict = Depends(common_pagination)):
    return pagination
```

```bash
curl "http://localhost:8000/items?skip=5&limit=3"
# {"skip":5,"limit":3}
```

FasterAPI resolves `common_pagination` first, then passes the result as `pagination`.

## Dependency parameters

Dependencies declare their own parameters exactly like route handlers — path, query,
header, cookie, body, or other dependencies:

```python
from FasterAPI import Header, HTTPException


async def verify_token(x_token: str = Header()):
    if x_token != "secret":
        raise HTTPException(status_code=403, detail="Invalid token")
    return x_token


@app.get("/protected")
async def protected_route(token: str = Depends(verify_token)):
    return {"token": token}
```

## Chained dependencies

```python
async def get_db():
    # imagine opening a DB connection
    return {"connected": True}


async def get_current_user(db: dict = Depends(get_db)):
    return {"user": "alice", "db": db}


@app.get("/me")
async def read_me(user: dict = Depends(get_current_user)):
    return user
```

## Class-based dependencies

Use `__call__` so the class instance is the callable:

```python
class RateLimiter:
    def __init__(self, max_calls: int) -> None:
        self.max_calls = max_calls
        self._counts: dict[str, int] = {}

    async def __call__(self, request: Request):
        ip = request.client[0] if request.client else "unknown"
        self._counts[ip] = self._counts.get(ip, 0) + 1
        if self._counts[ip] > self.max_calls:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")


limiter = RateLimiter(max_calls=100)


@app.get("/api/data")
async def get_data(_: None = Depends(limiter)):
    return {"data": "ok"}
```

## Dependency caching

By default, a dependency is **called once per request** even if multiple handlers
or sub-dependencies declare it. Disable with `use_cache=False`:

```python
Depends(get_db, use_cache=False)
```

## Dependencies without return value

Use `None` as the return type for side-effect-only dependencies (auth checks,
rate limiting):

```python
async def require_admin(token: str = Header(alias="x-admin-token")):
    if token != "admin-secret":
        raise HTTPException(status_code=403)


@app.delete("/users/{user_id}")
async def delete_user(user_id: int, _: None = Depends(require_admin)):
    return {"deleted": user_id}
```

## Multiple dependencies

```python
@app.get("/dashboard")
async def dashboard(
    user: dict = Depends(get_current_user),
    _: None = Depends(require_admin),
):
    return {"user": user}
```

## Next steps

- [Background Tasks](background-tasks.md) — defer work until after the response.
- [Advanced: Testing with Overrides](../advanced/testing-overrides.md) — replace
  dependencies in tests.
