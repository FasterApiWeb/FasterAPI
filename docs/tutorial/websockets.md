# WebSockets

FasterAPI supports WebSocket connections natively. Use the `@app.websocket` decorator
and the `WebSocket` class for full duplex, low-latency communication.

## Basic WebSocket endpoint

```python
from FasterAPI import Faster, WebSocket

app = Faster()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        data = await ws.receive_text()
        await ws.send_text(f"Echo: {data}")
```

Test it with a browser console:

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");
ws.onmessage = e => console.log(e.data);
ws.send("hello");
// logs: "Echo: hello"
```

## Receiving data

```python
# Text frames
text = await ws.receive_text()

# Binary frames
data = await ws.receive_bytes()

# Raw ASGI message dict
msg = await ws.receive()
```

## Sending data

```python
await ws.send_text("hello")
await ws.send_bytes(b"\x00\x01")
await ws.send_json({"type": "update", "payload": 42})
```

## Disconnection handling

`WebSocketDisconnect` is raised when the client closes the connection:

```python
from FasterAPI import WebSocketDisconnect


@app.websocket("/chat")
async def chat(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text()
            await ws.send_text(f"You said: {msg}")
    except WebSocketDisconnect:
        print("Client disconnected")
```

## Path parameters in WebSocket routes

```python
@app.websocket("/rooms/{room_id}")
async def room(ws: WebSocket, room_id: str):
    await ws.accept()
    await ws.send_text(f"Joined room {room_id}")
    await ws.close()
```

## Broadcast pattern

```python
from FasterAPI import WebSocket, WebSocketDisconnect

connections: list[WebSocket] = []


@app.websocket("/broadcast")
async def broadcast_endpoint(ws: WebSocket):
    await ws.accept()
    connections.append(ws)
    try:
        while True:
            msg = await ws.receive_text()
            for conn in list(connections):
                try:
                    await conn.send_text(msg)
                except Exception:
                    connections.remove(conn)
    except WebSocketDisconnect:
        connections.remove(ws)
```

## WebSocket state

```python
from FasterAPI import WebSocketState

if ws.client_state == WebSocketState.CONNECTED:
    await ws.send_text("still here")
```

States: `CONNECTING`, `CONNECTED`, `DISCONNECTED`.

## Closing with a code

```python
await ws.close(code=1008)  # Policy Violation
```

## Next steps

- [Metadata & Docs](metadata.md) — tag and describe your routes.
- [Advanced: Server-Sent Events](../advanced/server-sent-events.md) — one-way streaming.
