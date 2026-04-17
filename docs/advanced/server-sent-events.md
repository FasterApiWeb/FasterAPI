# Server-Sent Events (SSE)

Server-Sent Events (SSE) is a W3C standard for **one-way push** from server to
browser over a persistent HTTP connection — simpler than WebSockets when you only
need server-to-client updates.

## How SSE works

The client opens a regular `GET` request.  The server responds with
`Content-Type: text/event-stream` and streams newline-delimited event payloads
indefinitely.  The browser's `EventSource` API reconnects automatically on
disconnect.

## Basic SSE endpoint

```python
import asyncio
from FasterAPI import Faster, StreamingResponse

app = Faster()


async def event_generator():
    count = 0
    while True:
        count += 1
        yield f"data: count={count}\n\n".encode()
        await asyncio.sleep(1)


@app.get("/events")
async def sse_endpoint():
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering
        },
    )
```

## Event format

Each event is a block of `field: value` lines followed by a blank line:

```
data: hello world\n
\n

event: update\n
data: {"key":"value"}\n
id: 42\n
\n
```

Fields:

| Field | Purpose |
|---|---|
| `data` | Event payload (required) |
| `event` | Custom event type (default: `message`) |
| `id` | Last-event-ID for reconnect |
| `retry` | Reconnect delay in ms |

## Typed JSON events

```python
import json
import msgspec


async def stock_events():
    while True:
        price = {"symbol": "FAST", "price": 123.45}
        yield f"event: price\ndata: {json.dumps(price)}\n\n".encode()
        await asyncio.sleep(0.5)


@app.get("/stocks")
async def stock_stream():
    return StreamingResponse(stock_events(), media_type="text/event-stream")
```

## Client-side usage

```javascript
const source = new EventSource("/events");

source.onmessage = (e) => {
    console.log("Message:", e.data);
};

source.addEventListener("price", (e) => {
    const data = JSON.parse(e.data);
    console.log("Price update:", data);
});

source.onerror = () => {
    console.log("Connection lost, reconnecting...");
};
```

## Disconnect detection

The connection closes when the client disconnects, but the generator keeps yielding
until the next `await`. Check `request.is_disconnected()` or wrap in a try/except:

```python
from FasterAPI import Request


async def live_feed(request: Request):
    while True:
        if await request.is_disconnected():
            break
        yield b"data: tick\n\n"
        await asyncio.sleep(1)


@app.get("/feed")
async def feed(request: Request):
    return StreamingResponse(live_feed(request), media_type="text/event-stream")
```

## Multiple clients with a shared queue

```python
import asyncio
from collections import defaultdict

subscribers: dict[int, asyncio.Queue] = {}
_next_id = 0


def publish(message: str):
    for q in subscribers.values():
        q.put_nowait(message)


async def subscribe(request: Request):
    global _next_id
    _next_id += 1
    sid = _next_id
    subscribers[sid] = asyncio.Queue()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(subscribers[sid].get(), timeout=15)
                yield f"data: {msg}\n\n".encode()
            except asyncio.TimeoutError:
                yield b": keepalive\n\n"  # comment to prevent proxy timeout
    finally:
        del subscribers[sid]


@app.get("/notifications")
async def notifications(request: Request):
    return StreamingResponse(subscribe(request), media_type="text/event-stream")
```

## SSE vs WebSockets

| | SSE | WebSocket |
|---|---|---|
| Direction | Server → Client | Bidirectional |
| Protocol | HTTP | ws:// / wss:// |
| Auto-reconnect | Yes (browser) | No (manual) |
| Proxy support | Universal | Variable |
| Use case | Live feeds, notifications | Chat, gaming, collaboration |

## Next steps

- [WebSockets](../tutorial/websockets.md) — bidirectional real-time communication.
- [Custom Response Classes](custom-response.md) — StreamingResponse details.
