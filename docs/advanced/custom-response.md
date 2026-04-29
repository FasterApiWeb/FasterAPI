# Custom Response Classes

FasterAPI ships several response classes.  Return one directly from a route handler
for full control over status code, headers, content type, and body encoding.

## Response hierarchy

```
Response
├── JSONResponse      (msgspec.json.encode, application/json)
├── HTMLResponse      (text/html)
├── PlainTextResponse (text/plain)
└── RedirectResponse  (Location header, 307 by default)
StreamingResponse     (async/sync iterator)
FileResponse          (disk file, with Content-Disposition)
```

## JSONResponse

The default when you return a dict, struct, or primitive — but you can construct it
explicitly for custom status or headers:

```python
from FasterAPI import Faster, JSONResponse

app = Faster()


@app.get("/items")
async def get_items():
    return JSONResponse(
        content={"items": []},
        status_code=200,
        headers={"X-Total-Count": "0"},
    )
```

### Pre-serialised JSON (`bytes`)

If the JSON body is **fixed** (same bytes every time), pass UTF-8-encoded JSON as `bytes`
(or `bytearray` / `memoryview`) so the handler skips `msgspec` encoding on each request:

```python
_HEALTH_JSON = b'{"status":"ok"}'


@app.get("/health")
async def health():
    return JSONResponse(_HEALTH_JSON)
```

For shared caches across workers or TTL eviction, combine application-level caching or
`RedisCacheMiddleware` with encoded payloads where appropriate.

## HTMLResponse

```python
from FasterAPI import HTMLResponse


@app.get("/", response_class=HTMLResponse)
async def homepage():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html><body><h1>FasterAPI</h1></body></html>
    """)
```

## PlainTextResponse

```python
from FasterAPI import PlainTextResponse


@app.get("/health")
async def health():
    return PlainTextResponse("OK")
```

## RedirectResponse

```python
from FasterAPI import RedirectResponse


@app.get("/old-path")
async def old_path():
    return RedirectResponse(url="/new-path", status_code=301)
```

## StreamingResponse

Use an async generator to stream large responses without buffering the full body in
memory:

```python
import asyncio
from FasterAPI import StreamingResponse


async def large_csv():
    yield b"id,name\n"
    for i in range(1_000_000):
        yield f"{i},item-{i}\n".encode()
        if i % 1000 == 0:
            await asyncio.sleep(0)  # yield to event loop


@app.get("/export.csv")
async def export():
    return StreamingResponse(large_csv(), media_type="text/csv")
```

Sync iterators also work:

```python
def sync_stream():
    for chunk in read_chunks():
        yield chunk

StreamingResponse(sync_stream(), media_type="application/octet-stream")
```

## FileResponse

Serve a file from disk with automatic MIME-type detection:

```python
from FasterAPI import FileResponse


@app.get("/report")
async def download_report():
    return FileResponse(
        path="data/report.xlsx",
        filename="monthly-report.xlsx",  # Content-Disposition filename
    )
```

## Custom `Response` subclass

Build a response class for a non-standard content type:

```python
import msgpack
from FasterAPI.response import Response


class MsgPackResponse(Response):
    media_type = "application/msgpack"

    def _render(self, content):
        return msgpack.packb(content, use_bin_type=True)


@app.get("/data", response_class=MsgPackResponse)
async def packed_data():
    return MsgPackResponse({"key": "value"})
```

## Setting response headers in route handlers

```python
@app.get("/items")
async def items_with_etag():
    return JSONResponse(
        {"items": []},
        headers={"ETag": '"abc123"', "Cache-Control": "max-age=60"},
    )
```

## Next steps

- [Response Cookies & Headers](response-cookies-headers.md)
- [Server-Sent Events](server-sent-events.md) — streaming events to the browser.
