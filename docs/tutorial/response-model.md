# Response Model

FasterAPI serialises whatever you return from a route handler.  For tight control over
the shape of the response, annotate the **return type** and use `response_model` or
`status_code` in the decorator.

## Return type annotation

```python
import msgspec
from FasterAPI import Faster

app = Faster()


class Item(msgspec.Struct):
    id: int
    name: str
    price: float


@app.get("/items/{item_id}")
async def get_item(item_id: int) -> Item:
    return Item(id=item_id, name="Widget", price=9.99)
```

FasterAPI uses `msgspec.json.encode` to serialise the struct directly — no
intermediate dict conversion.

## Custom status codes

```python
@app.post("/items", status_code=201)
async def create_item(item: Item) -> Item:
    return item
```

Common status codes:

| Code | Meaning |
|------|---------|
| 200 | OK (default) |
| 201 | Created |
| 204 | No Content |
| 400 | Bad Request |
| 404 | Not Found |
| 422 | Unprocessable Entity |

## Returning `None` / no body (204)

```python
@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int) -> None:
    # delete logic here
    pass
```

## Returning a list

```python
@app.get("/items")
async def list_items() -> list[Item]:
    return [Item(id=1, name="alpha", price=1.0)]
```

## Response classes

Return any response class directly to take full control:

```python
from FasterAPI import JSONResponse, HTMLResponse, PlainTextResponse


@app.get("/json")
async def as_json():
    return JSONResponse({"key": "value"}, status_code=200)


@app.get("/html")
async def as_html():
    return HTMLResponse("<h1>Hello</h1>")


@app.get("/text")
async def as_text():
    return PlainTextResponse("Hello, world!")
```

## File responses

```python
from FasterAPI import FileResponse


@app.get("/download")
async def download():
    return FileResponse("report.pdf", filename="my-report.pdf")
```

## Streaming responses

```python
import asyncio
from FasterAPI import StreamingResponse


async def event_stream():
    for i in range(5):
        yield f"chunk {i}\n".encode()
        await asyncio.sleep(0.1)


@app.get("/stream")
async def stream():
    return StreamingResponse(event_stream(), media_type="text/plain")
```

## Additional responses in OpenAPI

Document alternative response shapes in the decorator:

```python
class ErrorDetail(msgspec.Struct):
    detail: str


@app.get(
    "/items/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def get_item(item_id: int) -> Item: ...
```

## Next steps

- [Error Handling](error-handling.md) — return standardised errors.
- [Advanced: Custom Response](../advanced/custom-response.md) — full response control.
