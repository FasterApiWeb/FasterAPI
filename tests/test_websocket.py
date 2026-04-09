import msgspec
import pytest
from FasterAPI.app import Faster
from FasterAPI.websocket import WebSocket, WebSocketDisconnect, WebSocketState

# --------------- helpers ---------------


class MockWebSocketTransport:
    """Simulates the ASGI websocket protocol for testing."""

    def __init__(self, to_receive: list[dict] | None = None):
        self._to_receive = list(to_receive or [])
        self.sent: list[dict] = []
        self._receive_idx = 0

    async def receive(self) -> dict:
        if self._receive_idx < len(self._to_receive):
            msg = self._to_receive[self._receive_idx]
            self._receive_idx += 1
            return msg
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(self, message: dict) -> None:
        self.sent.append(message)

    def accepted(self) -> bool:
        return any(m.get("type") == "websocket.accept" for m in self.sent)

    def sent_texts(self) -> list[str]:
        return [m["text"] for m in self.sent if m.get("type") == "websocket.send" and "text" in m]

    def sent_bytes(self) -> list[bytes]:
        return [m["bytes"] for m in self.sent if m.get("type") == "websocket.send" and "bytes" in m]

    def close_codes(self) -> list[int]:
        return [m.get("code", 1000) for m in self.sent if m.get("type") == "websocket.close"]


def _ws_scope(
    path: str = "/ws",
    headers: list[tuple[bytes, bytes]] | None = None,
    query_string: bytes = b"",
) -> dict:
    return {
        "type": "websocket",
        "path": path,
        "headers": headers or [],
        "query_string": query_string,
        "client": ("127.0.0.1", 9000),
    }


# ==============================
#  WebSocket constructor & props
# ==============================


class TestWebSocketProperties:
    def test_path_and_params(self):
        scope = _ws_scope(path="/chat")
        scope["path_params"] = {"room": "general"}
        ws = WebSocket(scope, None, None)
        assert ws.path == "/chat"
        assert ws.path_params == {"room": "general"}

    def test_headers_lowercased(self):
        scope = _ws_scope(headers=[(b"X-Token", b"abc"), (b"Authorization", b"Bearer xyz")])
        ws = WebSocket(scope, None, None)
        assert ws.headers["x-token"] == "abc"
        assert ws.headers["authorization"] == "Bearer xyz"

    def test_client(self):
        ws = WebSocket(_ws_scope(), None, None)
        assert ws.client == ("127.0.0.1", 9000)

    def test_client_absent(self):
        scope = _ws_scope()
        del scope["client"]
        ws = WebSocket(scope, None, None)
        assert ws.client is None

    def test_query_params_single(self):
        scope = _ws_scope(query_string=b"token=abc&room=dev")
        ws = WebSocket(scope, None, None)
        assert ws.query_params["token"] == "abc"
        assert ws.query_params["room"] == "dev"

    def test_query_params_empty(self):
        ws = WebSocket(_ws_scope(), None, None)
        assert ws.query_params == {}

    def test_initial_state_is_connecting(self):
        ws = WebSocket(_ws_scope(), None, None)
        assert ws._state == WebSocketState.CONNECTING


# ==============================
#  accept
# ==============================


class TestWebSocketAccept:
    @pytest.mark.asyncio
    async def test_accept(self):
        transport = MockWebSocketTransport()
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        await ws.accept()
        assert transport.accepted()
        assert ws._state == WebSocketState.CONNECTED

    @pytest.mark.asyncio
    async def test_accept_subprotocol(self):
        transport = MockWebSocketTransport()
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        await ws.accept(subprotocol="graphql-ws")
        assert transport.sent[0]["subprotocol"] == "graphql-ws"

    @pytest.mark.asyncio
    async def test_double_accept_raises(self):
        transport = MockWebSocketTransport()
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        await ws.accept()
        with pytest.raises(RuntimeError, match="not in CONNECTING state"):
            await ws.accept()


# ==============================
#  send / receive text
# ==============================


class TestWebSocketText:
    @pytest.mark.asyncio
    async def test_send_receive_text(self):
        transport = MockWebSocketTransport(
            to_receive=[
                {"type": "websocket.receive", "text": "hello"},
            ]
        )
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        text = await ws.receive_text()
        assert text == "hello"

        await ws.send_text("world")
        assert transport.sent_texts() == ["world"]

    @pytest.mark.asyncio
    async def test_receive_empty_text(self):
        transport = MockWebSocketTransport(
            to_receive=[
                {"type": "websocket.receive"},
            ]
        )
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        text = await ws.receive_text()
        assert text == ""


# ==============================
#  send / receive bytes
# ==============================


class TestWebSocketBytes:
    @pytest.mark.asyncio
    async def test_send_receive_bytes(self):
        transport = MockWebSocketTransport(
            to_receive=[
                {"type": "websocket.receive", "bytes": b"\x00\x01"},
            ]
        )
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        data = await ws.receive_bytes()
        assert data == b"\x00\x01"

        await ws.send_bytes(b"\x02\x03")
        assert transport.sent_bytes() == [b"\x02\x03"]


# ==============================
#  send / receive json
# ==============================


class TestWebSocketJson:
    @pytest.mark.asyncio
    async def test_send_receive_json(self):
        payload = msgspec.json.encode({"key": "value"}).decode()
        transport = MockWebSocketTransport(
            to_receive=[
                {"type": "websocket.receive", "text": payload},
            ]
        )
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        data = await ws.receive_json()
        assert data == {"key": "value"}

        await ws.send_json({"reply": True})
        sent = msgspec.json.decode(transport.sent_texts()[0].encode())
        assert sent == {"reply": True}

    @pytest.mark.asyncio
    async def test_send_json_list(self):
        transport = MockWebSocketTransport()
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        await ws.send_json([1, 2, 3])
        sent = msgspec.json.decode(transport.sent_texts()[0].encode())
        assert sent == [1, 2, 3]


# ==============================
#  close & disconnect
# ==============================


class TestWebSocketCloseDisconnect:
    @pytest.mark.asyncio
    async def test_close(self):
        transport = MockWebSocketTransport()
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.close(code=1001, reason="going away")
        assert transport.sent[-1] == {
            "type": "websocket.close",
            "code": 1001,
            "reason": "going away",
        }
        assert ws._state == WebSocketState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_close_default_code(self):
        transport = MockWebSocketTransport()
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.close()
        assert transport.close_codes() == [1000]

    @pytest.mark.asyncio
    async def test_disconnect_raises(self):
        transport = MockWebSocketTransport(
            to_receive=[
                {"type": "websocket.disconnect", "code": 1001},
            ]
        )
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive_text()
        assert exc_info.value.code == 1001
        assert ws._state == WebSocketState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_disconnect_default_code(self):
        transport = MockWebSocketTransport(
            to_receive=[
                {"type": "websocket.disconnect"},
            ]
        )
        ws = WebSocket(_ws_scope(), transport.receive, transport.send)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive_bytes()
        assert exc_info.value.code == 1000


# ==============================
#  App integration
# ==============================


class TestWebSocketApp:
    @pytest.mark.asyncio
    async def test_echo_handler(self):
        app = Faster(openapi_url=None)

        @app.websocket("/ws")
        async def echo(ws: WebSocket):
            await ws.accept()
            text = await ws.receive_text()
            await ws.send_text(f"echo: {text}")
            await ws.close()

        transport = MockWebSocketTransport(
            to_receive=[
                {"type": "websocket.receive", "text": "ping"},
            ]
        )
        await app(_ws_scope("/ws"), transport.receive, transport.send)

        assert transport.accepted()
        assert "echo: ping" in transport.sent_texts()
        assert len(transport.close_codes()) == 1

    @pytest.mark.asyncio
    async def test_no_route_closes_4004(self):
        app = Faster(openapi_url=None)
        transport = MockWebSocketTransport()
        await app(_ws_scope("/missing"), transport.receive, transport.send)

        assert transport.close_codes() == [4004]
        assert not transport.accepted()

    @pytest.mark.asyncio
    async def test_trailing_slash_tolerance(self):
        app = Faster(openapi_url=None)

        @app.websocket("/chat")
        async def chat(ws: WebSocket):
            await ws.accept()
            await ws.send_text("connected")
            await ws.close()

        transport = MockWebSocketTransport()
        await app(_ws_scope("/chat/"), transport.receive, transport.send)

        assert transport.accepted()
        assert "connected" in transport.sent_texts()

    @pytest.mark.asyncio
    async def test_json_roundtrip(self):
        app = Faster(openapi_url=None)

        @app.websocket("/api")
        async def api(ws: WebSocket):
            await ws.accept()
            data = await ws.receive_json()
            await ws.send_json({"received": data})
            await ws.close()

        payload = msgspec.json.encode({"msg": "hi"}).decode()
        transport = MockWebSocketTransport(
            to_receive=[
                {"type": "websocket.receive", "text": payload},
            ]
        )
        await app(_ws_scope("/api"), transport.receive, transport.send)

        sent = msgspec.json.decode(transport.sent_texts()[0].encode())
        assert sent == {"received": {"msg": "hi"}}

    @pytest.mark.asyncio
    async def test_multiple_ws_routes(self):
        app = Faster(openapi_url=None)

        @app.websocket("/a")
        async def route_a(ws: WebSocket):
            await ws.accept()
            await ws.send_text("a")
            await ws.close()

        @app.websocket("/b")
        async def route_b(ws: WebSocket):
            await ws.accept()
            await ws.send_text("b")
            await ws.close()

        t1 = MockWebSocketTransport()
        t2 = MockWebSocketTransport()
        await app(_ws_scope("/a"), t1.receive, t1.send)
        await app(_ws_scope("/b"), t2.receive, t2.send)

        assert t1.sent_texts() == ["a"]
        assert t2.sent_texts() == ["b"]

    @pytest.mark.asyncio
    async def test_multi_message_conversation(self):
        app = Faster(openapi_url=None)

        @app.websocket("/chat")
        async def chat(ws: WebSocket):
            await ws.accept()
            try:
                while True:
                    msg = await ws.receive_text()
                    await ws.send_text(f"reply: {msg}")
            except WebSocketDisconnect:
                pass

        transport = MockWebSocketTransport(
            to_receive=[
                {"type": "websocket.receive", "text": "first"},
                {"type": "websocket.receive", "text": "second"},
                {"type": "websocket.receive", "text": "third"},
                {"type": "websocket.disconnect", "code": 1000},
            ]
        )
        await app(_ws_scope("/chat"), transport.receive, transport.send)

        assert transport.sent_texts() == ["reply: first", "reply: second", "reply: third"]

    @pytest.mark.asyncio
    async def test_query_params_available_in_handler(self):
        app = Faster(openapi_url=None)

        @app.websocket("/ws")
        async def handler(ws: WebSocket):
            await ws.accept()
            token = ws.query_params.get("token", "none")
            await ws.send_text(f"token={token}")
            await ws.close()

        transport = MockWebSocketTransport()
        await app(
            _ws_scope("/ws", query_string=b"token=secret123"),
            transport.receive,
            transport.send,
        )

        assert transport.sent_texts() == ["token=secret123"]

    @pytest.mark.asyncio
    async def test_headers_available_in_handler(self):
        app = Faster(openapi_url=None)

        @app.websocket("/ws")
        async def handler(ws: WebSocket):
            await ws.accept()
            auth = ws.headers.get("authorization", "none")
            await ws.send_text(auth)
            await ws.close()

        transport = MockWebSocketTransport()
        await app(
            _ws_scope("/ws", headers=[(b"authorization", b"Bearer tok")]),
            transport.receive,
            transport.send,
        )

        assert transport.sent_texts() == ["Bearer tok"]
