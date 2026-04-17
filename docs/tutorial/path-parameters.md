# Path Parameters

Path parameters are **variable segments** inside the URL, written as `{name}` in the
route pattern.

## Basic path parameter

```python
from FasterAPI import Faster

app = Faster()


@app.get("/items/{item_id}")
async def read_item(item_id: str):
    return {"item_id": item_id}
```

```bash
curl http://localhost:8000/items/foo
# {"item_id":"foo"}
```

## Type coercion

Annotate the parameter with a Python type and FasterAPI will coerce the string from
the URL automatically. If the value cannot be converted, a **422** error is returned.

```python
@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}
```

```bash
curl http://localhost:8000/items/42    # {"item_id":42}
curl http://localhost:8000/items/abc   # 422 Unprocessable Entity
```

## Using `Path()` for extra validation

Import `Path` from `FasterAPI` to attach metadata (title, description) that appears
in the generated OpenAPI schema:

```python
from FasterAPI import Faster, Path

app = Faster()


@app.get("/users/{user_id}")
async def get_user(user_id: int = Path(description="The numeric ID of the user")):
    return {"user_id": user_id}
```

## Multiple path parameters

```python
@app.get("/users/{user_id}/items/{item_id}")
async def get_user_item(user_id: int, item_id: str):
    return {"user_id": user_id, "item_id": item_id}
```

## Path parameters and order

Static routes are matched before dynamic ones, so this works as expected:

```python
@app.get("/users/me")           # matched first
async def read_current_user():
    return {"user": "the current user"}


@app.get("/users/{user_id}")    # matched when /users/me does not apply
async def read_user(user_id: str):
    return {"user_id": user_id}
```

## Next steps

- [Query Parameters](query-parameters.md) — optional key-value pairs in the URL.
- [Request Body](request-body.md) — structured JSON input from the client.
