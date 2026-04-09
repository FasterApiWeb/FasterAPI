from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import msgspec.json

from .types import ASGIApp


class WebSocketState:
    """Enumeration of WebSocket connection states."""

    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


class WebSocketDisconnect(Exception):
    """Raised when a WebSocket connection is disconnected."""

    def __init__(self, code: int = 1000) -> None:
        self.code = code


class WebSocket:
    """Represents a WebSocket connection."""

    __slots__ = (
        "_scope",
        "_receive",
        "_send",
        "path",
        "path_params",
        "client",
        "headers",
        "query_params",
        "_state",
    )

    def __init__(self, scope: dict[str, Any], receive: ASGIApp, send: ASGIApp) -> None:
        self._scope = scope
        self._receive = receive
        self._send = send
        self._state = WebSocketState.CONNECTING
        self.path: str = scope.get("path", "/")
        self.path_params: dict[str, str] = scope.get("path_params", {})
        self.client: tuple[str, int] | None = scope.get("client")

        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        self.headers: dict[str, str] = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw_headers}

        qs = scope.get("query_string", b"")
        parsed = parse_qs(qs.decode("latin-1") if isinstance(qs, bytes) else qs)
        self.query_params: dict[str, Any] = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    async def accept(self, subprotocol: str | None = None) -> None:
        """Accept the WebSocket connection, optionally selecting a subprotocol."""
        if self._state != WebSocketState.CONNECTING:
            raise RuntimeError("WebSocket is not in CONNECTING state")
        msg: dict[str, Any] = {"type": "websocket.accept"}
        if subprotocol is not None:
            msg["subprotocol"] = subprotocol
        await self._send(msg)
        self._state = WebSocketState.CONNECTED

    async def _receive_message(self) -> dict[str, Any]:
        message: dict[str, Any] = await self._receive()
        if message["type"] == "websocket.disconnect":
            self._state = WebSocketState.DISCONNECTED
            raise WebSocketDisconnect(message.get("code", 1000))
        return message

    async def receive_text(self) -> str:
        """Receive a text message from the WebSocket."""
        message = await self._receive_message()
        return str(message.get("text", ""))

    async def receive_bytes(self) -> bytes:
        """Receive a binary message from the WebSocket."""
        message = await self._receive_message()
        result = message.get("bytes", b"")
        return bytes(result) if not isinstance(result, bytes) else result

    async def receive_json(self) -> Any:
        """Receive a message from the WebSocket and parse it as JSON."""
        text = await self.receive_text()
        return msgspec.json.decode(text.encode())

    async def send_text(self, data: str) -> None:
        """Send a text message through the WebSocket."""
        await self._send({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        """Send a binary message through the WebSocket."""
        await self._send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any) -> None:
        """Send data as a JSON-encoded text message through the WebSocket."""
        encoded = msgspec.json.encode(data)
        await self.send_text(encoded.decode())

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the WebSocket connection."""
        await self._send({"type": "websocket.close", "code": code, "reason": reason})
        self._state = WebSocketState.DISCONNECTED
