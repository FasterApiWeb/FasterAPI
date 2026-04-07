from __future__ import annotations

from typing import Any, Callable
from urllib.parse import parse_qs

import msgspec.json


class WebSocketState:
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


class WebSocketDisconnect(Exception):
    def __init__(self, code: int = 1000) -> None:
        self.code = code


class WebSocket:
    __slots__ = (
        "_scope", "_receive", "_send", "path", "path_params",
        "client", "headers", "query_params", "_state",
    )

    def __init__(self, scope: dict, receive: Callable, send: Callable) -> None:
        self._scope = scope
        self._receive = receive
        self._send = send
        self._state = WebSocketState.CONNECTING
        self.path: str = scope.get("path", "/")
        self.path_params: dict[str, str] = scope.get("path_params", {})
        self.client: tuple[str, int] | None = scope.get("client")

        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        self.headers: dict[str, str] = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in raw_headers
        }

        qs = scope.get("query_string", b"")
        parsed = parse_qs(qs.decode("latin-1") if isinstance(qs, bytes) else qs)
        self.query_params: dict[str, str] = {
            k: v[0] if len(v) == 1 else v
            for k, v in parsed.items()
        }

    async def accept(self, subprotocol: str | None = None) -> None:
        if self._state != WebSocketState.CONNECTING:
            raise RuntimeError("WebSocket is not in CONNECTING state")
        msg: dict[str, Any] = {"type": "websocket.accept"}
        if subprotocol is not None:
            msg["subprotocol"] = subprotocol
        await self._send(msg)
        self._state = WebSocketState.CONNECTED

    async def _receive_message(self) -> dict:
        message = await self._receive()
        if message["type"] == "websocket.disconnect":
            self._state = WebSocketState.DISCONNECTED
            raise WebSocketDisconnect(message.get("code", 1000))
        return message

    async def receive_text(self) -> str:
        message = await self._receive_message()
        return message.get("text", "")

    async def receive_bytes(self) -> bytes:
        message = await self._receive_message()
        return message.get("bytes", b"")

    async def receive_json(self) -> Any:
        text = await self.receive_text()
        return msgspec.json.decode(text.encode())

    async def send_text(self, data: str) -> None:
        await self._send({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        await self._send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any) -> None:
        encoded = msgspec.json.encode(data)
        await self.send_text(encoded.decode())

    async def close(self, code: int = 1000, reason: str = "") -> None:
        await self._send({"type": "websocket.close", "code": code, "reason": reason})
        self._state = WebSocketState.DISCONNECTED
