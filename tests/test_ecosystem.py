"""Tests for v0.3 ecosystem integrations (optional dependencies)."""

from __future__ import annotations

import asyncio

import pytest
from FasterAPI import Depends, Faster, HTTPException, JWTBearer, OAuth2PasswordRequestForm
from FasterAPI.cli import main
from FasterAPI.jwt_auth import (
    create_access_token,
    oauth2_access_token_json,
    oauth2_password_token_response,
)
from FasterAPI.redis_cache import RedisCacheMiddleware
from FasterAPI.sqlalchemy_ext import sqlalchemy_session_dependency
from FasterAPI.testclient import TestClient


def test_cli_version_exits_zero(capsys):
    rc = main(["version"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert len(out) > 0


def test_create_access_token_and_jwt_bearer():
    secret = "unit-test-secret-key-minimum-length"
    tok = create_access_token("user-1", secret, expires_minutes=15)
    assert isinstance(tok, str)

    app = Faster()
    bearer = JWTBearer(secret=secret)

    @app.get("/who")
    async def who(claims: dict = Depends(bearer)):
        return {"sub": claims.get("sub")}

    client = TestClient(app)
    r = client.get("/who", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["sub"] == "user-1"


def test_oauth2_access_token_json_shape():
    body = oauth2_access_token_json("abc", expires_in=3600)
    assert body["access_token"] == "abc"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600


@pytest.mark.asyncio
async def test_oauth2_password_token_response_helper():
    async def auth_ok(u: str, p: str) -> str | None:
        if u == "a" and p == "b":
            return "uid-9"
        return None

    form = OAuth2PasswordRequestForm(username="a", password="b")
    body = await oauth2_password_token_response(form, secret="x" * 32, authenticate=auth_ok)
    assert "access_token" in body

    bad = OAuth2PasswordRequestForm(username="a", password="wrong")
    with pytest.raises(HTTPException) as ei:
        await oauth2_password_token_response(bad, secret="x" * 32, authenticate=auth_ok)
    assert ei.value.status_code == 401


def test_sqlalchemy_async_session_dependency_sqlite():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    pytest.importorskip("aiosqlite")
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    get_session = sqlalchemy_session_dependency(SessionLocal)

    async def setup_schema():
        async with engine.begin() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))

    asyncio.run(setup_schema())

    app = Faster()

    @app.get("/dbping")
    async def dbping(session=Depends(get_session)):
        await session.execute(text("SELECT 1"))
        return {"db": "ok"}

    client = TestClient(app)
    assert client.get("/dbping").status_code == 200


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = value


def test_redis_cache_hit_second_request():
    fake = _FakeRedis()
    inner = Faster()

    @inner.get("/cached")
    async def cached():
        return {"n": 42}

    app = RedisCacheMiddleware(inner, redis_client=fake, ttl=60)

    client = TestClient(app)
    r1 = client.get("/cached")
    assert r1.status_code == 200
    r2 = client.get("/cached")
    assert r2.status_code == 200
    assert r2.json() == {"n": 42}
    assert len(fake.store) >= 1
