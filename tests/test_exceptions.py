"""HTTP and validation exception types and default handlers."""

import pytest
from FasterAPI.exceptions import (
    HTTPException,
    RequestValidationError,
    _default_http_exception_handler,
    _default_validation_exception_handler,
)


def test_http_exception_attrs():
    e = HTTPException(418, detail="teapot", headers={"X": "y"})
    assert e.status_code == 418
    assert e.detail == "teapot"
    assert "418" in repr(e)


def test_validation_repr():
    e = RequestValidationError([{"loc": ["body"], "msg": "bad", "type": "x"}])
    assert "errors" in repr(e)


@pytest.mark.asyncio
async def test_default_http_handler_with_headers():
    exc = HTTPException(401, detail="nope", headers={"WWW-Authenticate": "Bearer"})
    status, body, hdrs = await _default_http_exception_handler(None, exc)
    assert status == 401
    assert b"nope" in body
    hmap = dict(hdrs)
    assert hmap[b"content-type"] == b"application/json"
    assert hmap[b"www-authenticate"] == b"Bearer"


@pytest.mark.asyncio
async def test_validation_handler_shapes_errors():
    exc = RequestValidationError(
        [
            {"loc": ["query", "q"], "msg": "missing", "type": "value_error"},
            {"loc": [], "msg": "x"},
        ]
    )
    status, body, hdrs = await _default_validation_exception_handler(None, exc)
    assert status == 422
    assert b"query" in body
