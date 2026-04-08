"""WebSocket chat room with broadcast and REST status endpoint.

Run:
    python examples/websocket_app.py

Endpoints:
    GET  /              — HTML chat UI (open in a browser)
    GET  /status        — JSON with connected client count
    WS   /ws/chat       — WebSocket chat (broadcast to all clients)

Open multiple browser tabs to http://localhost:8000/ to test the chat.
"""

from FasterAPI import Faster, HTMLResponse, WebSocket, WebSocketDisconnect

app = Faster(
    title="WebSocket Chat",
    version="1.0.0",
    description="Real-time chat room using WebSocket broadcast",
)


# ── Connection manager ──

class ConnectionManager:
    """Track active WebSocket connections and broadcast messages."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)

    async def broadcast(self, message: str) -> None:
        for conn in list(self._connections):
            try:
                await conn.send_text(message)
            except Exception:
                self._connections.remove(conn)

    @property
    def count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


# ── WebSocket chat endpoint ──

@app.websocket("/ws/chat")
async def chat(ws: WebSocket):
    await manager.connect(ws)
    await manager.broadcast(f"[system] A user joined. ({manager.count} online)")
    try:
        while True:
            text = await ws.receive_text()
            await manager.broadcast(text)
    except WebSocketDisconnect:
        manager.disconnect(ws)
        await manager.broadcast(f"[system] A user left. ({manager.count} online)")


# ── REST status endpoint ──

@app.get("/status", tags=["status"], summary="Connected clients")
async def status():
    """Return the number of currently connected WebSocket clients."""
    return {"connected": manager.count}


# ── Simple HTML chat UI ──

CHAT_HTML = """<!DOCTYPE html>
<html>
<head><title>FasterAPI Chat</title>
<style>
  body { font-family: sans-serif; max-width: 600px; margin: 40px auto; }
  #log { border: 1px solid #ccc; height: 300px; overflow-y: auto; padding: 8px;
         margin-bottom: 8px; background: #fafafa; }
  #msg { width: 80%; padding: 6px; }
  button { padding: 6px 16px; }
  .system { color: #888; font-style: italic; }
</style>
</head>
<body>
  <h2>FasterAPI Chat Room</h2>
  <div id="log"></div>
  <input id="msg" placeholder="Type a message..." autocomplete="off" />
  <button onclick="send()">Send</button>
  <script>
    const log = document.getElementById('log');
    const input = document.getElementById('msg');
    const ws = new WebSocket(`ws://${location.host}/ws/chat`);

    ws.onmessage = (e) => {
      const div = document.createElement('div');
      div.textContent = e.data;
      if (e.data.startsWith('[system]')) div.className = 'system';
      log.appendChild(div);
      log.scrollTop = log.scrollHeight;
    };

    ws.onclose = () => {
      const div = document.createElement('div');
      div.textContent = '[disconnected]';
      div.className = 'system';
      log.appendChild(div);
    };

    function send() {
      const text = input.value.trim();
      if (text) { ws.send(text); input.value = ''; }
    }

    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
  </script>
</body>
</html>"""


@app.get("/", summary="Chat UI")
async def chat_ui():
    """Serve a minimal HTML chat client."""
    return HTMLResponse(CHAT_HTML)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
