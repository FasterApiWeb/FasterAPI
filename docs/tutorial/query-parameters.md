# Query Parameters

Query parameters are the key-value pairs that appear after `?` in a URL:

```
/items?skip=0&limit=10
```

Any function parameter that is **not** a path parameter and **not** typed as a
`msgspec.Struct` is treated as a query parameter.

## Basic query parameters

```python
from FasterAPI import Faster

app = Faster()

fake_db = [{"name": "alpha"}, {"name": "beta"}, {"name": "gamma"}]


@app.get("/items")
async def list_items(skip: int = 0, limit: int = 10):
    return fake_db[skip : skip + limit]
```

```bash
curl "http://localhost:8000/items?skip=1&limit=2"
# [{"name":"beta"},{"name":"gamma"}]
```

Both `skip` and `limit` have **defaults**, so they are optional.

## Required query parameters

Omit the default to make a parameter required:

```python
@app.get("/search")
async def search(q: str):
    return {"query": q}
```

Calling `/search` without `?q=...` returns a **422** validation error.

## Optional query parameters

Use `str | None` with a default of `None`:

```python
@app.get("/items/{item_id}")
async def get_item(item_id: int, detail: str | None = None):
    result: dict = {"item_id": item_id}
    if detail:
        result["detail"] = detail
    return result
```

## Boolean query parameters

FasterAPI understands several string representations of booleans:
`true`, `1`, `on`, `yes` → `True`; `false`, `0`, `off`, `no` → `False`.

```python
@app.get("/items")
async def list_items(active: bool = True):
    return {"active": active}
```

```bash
curl "http://localhost:8000/items?active=false"
# {"active":false}
```

## Using `Query()` for extra metadata

```python
from FasterAPI import Faster, Query

app = Faster()


@app.get("/items")
async def list_items(
    q: str | None = Query(default=None, description="Search term", alias="search"),
):
    return {"q": q}
```

The `alias` means the URL uses `?search=...` while the Python variable is `q`.

## Multiple values for the same key

Declare the type as `list[str]` to collect all values:

```python
@app.get("/filter")
async def filter_items(tags: list[str] = Query(default=[])):
    return {"tags": tags}
```

```bash
curl "http://localhost:8000/filter?tags=a&tags=b"
# {"tags":["a","b"]}
```

## Next steps

- [Request Body](request-body.md) — send structured data in the request body.
- [Path Parameters](path-parameters.md) — dynamic URL segments.
