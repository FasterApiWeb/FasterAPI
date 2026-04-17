# Using the Request Directly

Declare a parameter of type `Request` in a route handler to access the raw request
object — headers, cookies, query string, body, and client information.

## Importing and using `Request`

```python
from FasterAPI import Faster, Request

app = Faster()


@app.get("/info")
async def request_info(request: Request):
    return {
        "method": request.method,
        "url": str(request.url),
        "client": request.client,
        "headers": dict(request.headers),
    }
```

## Available attributes

| Attribute | Type | Description |
|---|---|---|
| `request.method` | `str` | HTTP verb (`GET`, `POST`, …) |
| `request.url` | `URL` | Full URL object |
| `request.headers` | `Headers` | Request headers (case-insensitive) |
| `request.query_params` | `QueryParams` | Parsed query string |
| `request.cookies` | `dict[str, str]` | Parsed `Cookie` header |
| `request.client` | `tuple[str, int] \| None` | `(host, port)` of the client |
| `request.path_params` | `dict[str, str]` | Matched path parameters |

## Reading headers

```python
@app.get("/echo-ua")
async def echo_user_agent(request: Request):
    ua = request.headers.get("user-agent", "unknown")
    return {"user_agent": ua}
```

## Reading the body

```python
@app.post("/raw-body")
async def raw_body(request: Request):
    body = await request.body()   # bytes
    return {"size": len(body)}
```

### JSON body

```python
@app.post("/parse-json")
async def parse_json(request: Request):
    data = await request.json()   # raises on invalid JSON
    return {"received": data}
```

### Form data

```python
@app.post("/raw-form")
async def raw_form(request: Request):
    form = await request.form()
    return {k: v for k, v in form.items() if not hasattr(v, "read")}
```

## Query parameters

```python
@app.get("/search")
async def search(request: Request):
    q = request.query_params.get("q", "")
    page = int(request.query_params.get("page", 1))
    return {"q": q, "page": page}
```

## Client IP address

```python
@app.get("/ip")
async def client_ip(request: Request):
    if request.client:
        host, port = request.client
        return {"ip": host, "port": port}
    return {"ip": None}
```

When behind a reverse proxy, check the `X-Forwarded-For` header:

```python
@app.get("/real-ip")
async def real_ip(request: Request):
    forwarded_for = request.headers.get("x-forwarded-for")
    ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client[0] if request.client else None
    )
    return {"ip": ip}
```

## Combining `Request` with typed parameters

`Request` can coexist with any other parameter types:

```python
@app.post("/items/{item_id}")
async def create_item(
    item_id: int,
    item: Item,
    request: Request,
):
    ua = request.headers.get("user-agent", "")
    return {"item_id": item_id, "name": item.name, "ua": ua}
```

## Next steps

- [Settings & Environment Variables](settings.md) — configure your app from the environment.
- [Behind a Proxy](behind-proxy.md) — handle forwarded headers correctly.
