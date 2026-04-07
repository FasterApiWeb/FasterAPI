from __future__ import annotations

import asyncio
from typing import Any, Callable

import httpx


class TestClient:
    def __init__(self, app: Callable) -> None:
        self.app = app
        self._transport = httpx.ASGITransport(app=app)
        self._client = httpx.AsyncClient(
            transport=self._transport,
            base_url="http://testserver",
        )

    def _run(self, coro: Any) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._run(self._client.get(url, **kwargs))

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._run(self._client.post(url, **kwargs))

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._run(self._client.put(url, **kwargs))

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._run(self._client.delete(url, **kwargs))

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._run(self._client.patch(url, **kwargs))

    def options(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._run(self._client.options(url, **kwargs))

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._run(self._client.head(url, **kwargs))
