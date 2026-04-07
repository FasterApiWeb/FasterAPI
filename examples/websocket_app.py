"""WebSocket echo server example."""

from FasterAPI.app import Faster
from FasterAPI.websocket import WebSocket, WebSocketDisconnect

app = Faster(title="WebSocket App", version="1.0.0")


@app.get("/")
async def root():
    return {"message": "Visit /ws to connect via WebSocket"}


@app.websocket("/ws")
async def websocket_echo(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            text = await ws.receive_text()
            await ws.send_text(f"echo: {text}")
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/json")
async def websocket_json(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            await ws.send_json({"received": data, "status": "ok"})
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
