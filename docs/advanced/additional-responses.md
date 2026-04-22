# Additional Responses in OpenAPI

Route decorators accept a `responses` parameter that lets you document extra HTTP
status codes beyond the primary one.  Swagger UI renders each code with its schema
and description.

## Declaring additional responses

```python
import msgspec
from FasterAPI import Faster, HTTPException

app = Faster()


class Item(msgspec.Struct):
    id: int
    name: str


class ErrorDetail(msgspec.Struct):
    detail: str


@app.get(
    "/items/{item_id}",
    response_model=Item,
    responses={
        404: {"model": ErrorDetail, "description": "Item not found"},
        422: {"description": "Validation error — item_id must be a positive integer"},
    },
)
async def get_item(item_id: int):
    if item_id <= 0:
        raise HTTPException(status_code=422, detail="item_id must be positive")
    if item_id > 1000:
        raise HTTPException(status_code=404, detail="Item not found")
    return Item(id=item_id, name="Widget")
```

The `response_model` on the decorator describes the **200 OK** body.  The `responses`
dict adds the other codes; each value can contain:

| Key | Type | Purpose |
|---|---|---|
| `model` | msgspec Struct class | Schema to generate for this status code |
| `description` | `str` | Human-readable explanation |
| `content` | `dict` | Explicit media-type map (overrides `model`) |
| `headers` | `dict` | Response header schemas |

## Sharing an error model across routes

Define a reusable error struct and reference it everywhere:

```python
class ProblemDetail(msgspec.Struct):
    """RFC 9457-style error body."""
    type: str
    title: str
    status: int
    detail: str | None = None


COMMON_ERRORS = {
    400: {"model": ProblemDetail, "description": "Bad request"},
    401: {"model": ProblemDetail, "description": "Unauthenticated"},
    403: {"model": ProblemDetail, "description": "Forbidden"},
    500: {"model": ProblemDetail, "description": "Internal server error"},
}


@app.get("/users/{user_id}", response_model=User, responses=COMMON_ERRORS)
async def get_user(user_id: int):
    ...


@app.post("/users", response_model=User, status_code=201, responses=COMMON_ERRORS)
async def create_user(body: CreateUser):
    ...
```

## Documenting response headers

```python
@app.post(
    "/items",
    status_code=201,
    responses={
        201: {
            "description": "Item created",
            "headers": {
                "Location": {
                    "schema": {"type": "string"},
                    "description": "URL of the newly created item",
                },
                "X-Request-ID": {
                    "schema": {"type": "string", "format": "uuid"},
                    "description": "Idempotency key echoed back",
                },
            },
        }
    },
)
async def create_item(body: CreateItem):
    item_id = await db.insert(body)
    from FasterAPI import Response
    return Response(
        status_code=201,
        headers={"Location": f"/items/{item_id}"},
    )
```

## Multiple content types

Use `content` when a route can return different media types depending on the
`Accept` header:

```python
@app.get(
    "/report",
    responses={
        200: {
            "description": "Report data",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Report"}},
                "text/csv": {"schema": {"type": "string"}},
            },
        }
    },
)
async def get_report(accept: str = "application/json"):
    ...
```

## Default response — covering all undocumented codes

OpenAPI allows a special `"default"` key that represents any status code not
explicitly listed:

```python
@app.delete(
    "/items/{item_id}",
    status_code=204,
    responses={
        204: {"description": "Deleted successfully"},
        "default": {"model": ProblemDetail, "description": "Unexpected error"},
    },
)
async def delete_item(item_id: int):
    ...
```

## Next steps

- [OpenAPI Customisation](openapi-customization.md) — extend or override the full schema.
- [Custom Response Classes](custom-response.md) — return non-JSON responses.
- [Error Handling](../tutorial/error-handling.md) — raise `HTTPException` with detail bodies.
