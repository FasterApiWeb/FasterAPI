# Error Handling

FasterAPI provides two built-in exception types and lets you register custom handlers
for any exception class.

## HTTPException

Raise `HTTPException` anywhere in a handler to return an HTTP error response:

```python
from FasterAPI import Faster, HTTPException

app = Faster()

items = {"foo": "The Foo item"}


@app.get("/items/{item_id}")
async def get_item(item_id: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item": items[item_id]}
```

```bash
curl http://localhost:8000/items/bar
# HTTP 404
# {"detail":"Item not found"}
```

You can pass any JSON-serialisable value as `detail`:

```python
raise HTTPException(
    status_code=422,
    detail={"field": "price", "msg": "must be positive"},
)
```

## Custom response headers

```python
raise HTTPException(
    status_code=401,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)
```

## RequestValidationError

Raised automatically when request data fails validation (e.g. wrong type, missing
required field).  The default handler returns a **422** with a structured error body:

```json
{
  "detail": [
    {
      "loc": ["body"],
      "msg": "Expected `int`, got `str` - at `$.item_id`",
      "type": "value_error.msgspec"
    }
  ]
}
```

## Custom exception handlers

Register a handler for any exception class via `add_exception_handler`:

```python
from FasterAPI import Faster, Request, HTTPException
from FasterAPI.response import JSONResponse

app = Faster()


class ItemNotFoundError(Exception):
    def __init__(self, item_id: int) -> None:
        self.item_id = item_id


def item_not_found_handler(request: Request, exc: ItemNotFoundError):
    return JSONResponse(
        {"detail": f"Item {exc.item_id} does not exist"},
        status_code=404,
    )


app.add_exception_handler(ItemNotFoundError, item_not_found_handler)


@app.get("/items/{item_id}")
async def get_item(item_id: int):
    raise ItemNotFoundError(item_id)
```

Async handlers are also supported:

```python
async def async_handler(request: Request, exc: ValueError):
    return JSONResponse({"error": str(exc)}, status_code=400)

app.add_exception_handler(ValueError, async_handler)
```

## Override built-in handlers

Override validation or HTTP exception behaviour the same way:

```python
from FasterAPI.exceptions import RequestValidationError


async def custom_validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        {"errors": exc.errors, "hint": "Check your request body"},
        status_code=422,
    )

app.add_exception_handler(RequestValidationError, custom_validation_handler)
```

## Exception handler precedence

Handlers are matched against `type(exc).__mro__`, so a handler for a base class
catches subclass exceptions when no more-specific handler is registered.

## Next steps

- [Dependencies](dependencies.md) — reuse auth/validation logic.
- [Middleware](middleware.md) — intercept all requests including error paths.
