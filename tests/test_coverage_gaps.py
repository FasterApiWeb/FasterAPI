"""Tests to cover staticfiles.py, templating.py, and security edge cases."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from FasterAPI import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    Depends,
    Faster,
    HTTPBasic,
    HTTPBasicCredentials,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
    Request,
    SecurityScopes,
    StaticFiles,
)
from FasterAPI.testclient import TestClient

# ---------------------------------------------------------------------------
#  StaticFiles
# ---------------------------------------------------------------------------


def _make_static_dir() -> tempfile.TemporaryDirectory:  # type: ignore[type-arg]
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    (root / "hello.txt").write_text("Hello, world!")
    (root / "style.css").write_text("body { color: red; }")
    sub = root / "sub"
    sub.mkdir()
    (sub / "index.html").write_text("<h1>Sub Index</h1>")
    (root / "index.html").write_text("<h1>Root Index</h1>")
    return td


def test_staticfiles_serve_text_file():
    with _make_static_dir() as td:
        app = Faster()
        app.mount("/static", StaticFiles(directory=td))

        client = TestClient(app)
        resp = client.get("/static/hello.txt")
        assert resp.status_code == 200
        assert resp.text == "Hello, world!"
        assert "text/plain" in resp.headers["content-type"]


def test_staticfiles_serve_css_file():
    with _make_static_dir() as td:
        app = Faster()
        app.mount("/static", StaticFiles(directory=td))

        client = TestClient(app)
        resp = client.get("/static/style.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]


def test_staticfiles_not_found():
    with _make_static_dir() as td:
        app = Faster()
        app.mount("/static", StaticFiles(directory=td))

        client = TestClient(app)
        resp = client.get("/static/missing.txt")
        assert resp.status_code == 404


def test_staticfiles_method_not_allowed():
    with _make_static_dir() as td:
        app = Faster()
        app.mount("/static", StaticFiles(directory=td))

        client = TestClient(app)
        resp = client.post("/static/hello.txt")
        assert resp.status_code == 405


def test_staticfiles_directory_no_html():
    with _make_static_dir() as td:
        app = Faster()
        app.mount("/static", StaticFiles(directory=td, html=False))

        client = TestClient(app)
        resp = client.get("/static/sub/")
        assert resp.status_code == 404


def test_staticfiles_directory_with_html():
    with _make_static_dir() as td:
        app = Faster()
        app.mount("/static", StaticFiles(directory=td, html=True))

        client = TestClient(app)
        resp = client.get("/static/sub/")
        assert resp.status_code == 200
        assert "Sub Index" in resp.text


def test_staticfiles_root_index_html():
    with _make_static_dir() as td:
        app = Faster()
        app.mount("/static", StaticFiles(directory=td, html=True))

        client = TestClient(app)
        resp = client.get("/static/")
        assert resp.status_code == 200
        assert "Root Index" in resp.text


def test_staticfiles_path_traversal_blocked():
    with _make_static_dir() as td:
        app = Faster()
        app.mount("/static", StaticFiles(directory=td))

        client = TestClient(app)
        resp = client.get("/static/../../../etc/passwd")
        assert resp.status_code == 404


def test_staticfiles_missing_directory_raises():
    with pytest.raises(RuntimeError, match="does not exist"):
        StaticFiles(directory="/nonexistent/path/that/does/not/exist")


def test_staticfiles_check_dir_false():
    # Should not raise even if directory doesn't exist when check_dir=False
    sf = StaticFiles(directory="/nonexistent", check_dir=False)
    assert sf.directory == Path("/nonexistent")


def test_staticfiles_head_method():
    with _make_static_dir() as td:
        app = Faster()
        app.mount("/static", StaticFiles(directory=td))

        client = TestClient(app)
        resp = client.head("/static/hello.txt")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
#  Jinja2Templates
# ---------------------------------------------------------------------------


def _make_template_dir() -> tempfile.TemporaryDirectory:  # type: ignore[type-arg]
    td = tempfile.TemporaryDirectory()
    (Path(td.name) / "hello.html").write_text("<h1>Hello {{ name }}!</h1>")
    (Path(td.name) / "simple.html").write_text("<p>Simple</p>")
    return td


def test_jinja2_template_response():
    try:
        import jinja2  # noqa: F401
    except ImportError:
        pytest.skip("jinja2 not installed")

    from FasterAPI import Jinja2Templates

    with _make_template_dir() as td:
        templates = Jinja2Templates(directory=td)
        app = Faster()

        @app.get("/hello/{name}")
        async def hello(request: Request, name: str):
            return templates.TemplateResponse(request, "hello.html", {"name": name})

        client = TestClient(app)
        resp = client.get("/hello/World")
        assert resp.status_code == 200
        assert "<h1>Hello World!</h1>" in resp.text


def test_jinja2_template_response_status_code():
    try:
        import jinja2  # noqa: F401
    except ImportError:
        pytest.skip("jinja2 not installed")

    from FasterAPI import Jinja2Templates

    with _make_template_dir() as td:
        templates = Jinja2Templates(directory=td)
        app = Faster()

        @app.get("/simple")
        async def simple(request: Request):
            return templates.TemplateResponse(request, "simple.html", status_code=201)

        client = TestClient(app)
        resp = client.get("/simple")
        assert resp.status_code == 201
        assert "<p>Simple</p>" in resp.text


def test_jinja2_get_template():
    try:
        import jinja2  # noqa: F401
    except ImportError:
        pytest.skip("jinja2 not installed")

    from FasterAPI import Jinja2Templates

    with _make_template_dir() as td:
        templates = Jinja2Templates(directory=td)
        tmpl = templates.get_template("hello.html")
        rendered = tmpl.render({"name": "Test"})
        assert "Hello Test" in rendered


def test_jinja2_missing_import():
    import sys

    jinja2_backup = sys.modules.pop("jinja2", None)
    try:
        from FasterAPI.templating import Jinja2Templates as J2T

        with _make_template_dir() as td:
            t = J2T(directory=td)
            assert t.env is not None
    finally:
        if jinja2_backup is not None:
            sys.modules["jinja2"] = jinja2_backup


# ---------------------------------------------------------------------------
#  Security edge cases (missing coverage)
# ---------------------------------------------------------------------------


def test_security_scopes_repr():
    scopes = SecurityScopes(["read", "write"])
    assert "read" in repr(scopes)


def test_oauth2_form_instantiation_with_scope():
    form = OAuth2PasswordRequestForm(
        grant_type="password",
        username="user",
        password="pass",
        scope="read write",
        client_id="client",
        client_secret="secret",
    )
    assert form.username == "user"
    assert form.scopes == ["read", "write"]
    assert form.client_id == "client"


def test_oauth2_form_empty_scope():
    form = OAuth2PasswordRequestForm(username="u", password="p")
    assert form.scopes == []


def test_oauth2_form_from_request():
    app = Faster()

    @app.post("/token")
    async def token(form: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm)):
        return {"username": form.username, "scopes": form.scopes}

    client = TestClient(app)
    resp = client.post(
        "/token",
        data={"username": "alice", "password": "secret", "scope": "read write"},
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"
    assert "read" in resp.json()["scopes"]


def test_http_basic_credentials_repr():
    creds = HTTPBasicCredentials(username="alice", password="secret")
    assert "alice" in repr(creds)


def test_http_basic_invalid_base64():
    http_basic = HTTPBasic()
    app = Faster()

    @app.get("/protected")
    async def protected(creds: HTTPBasicCredentials = Depends(http_basic)):
        return {"username": creds.username}

    client = TestClient(app)
    resp = client.get("/protected", headers={"Authorization": "Basic not-valid-base64!!!"})
    assert resp.status_code in (400, 401)


def test_api_key_header_missing_auto_error_false():
    api_key = APIKeyHeader(name="X-API-Key", auto_error=False)
    app = Faster()

    @app.get("/secure")
    async def secure(key: str | None = Depends(api_key)):
        return {"key": key}

    client = TestClient(app)
    resp = client.get("/secure")
    assert resp.status_code == 200
    assert resp.json()["key"] is None


def test_api_key_query_missing_auto_error_false():
    api_key = APIKeyQuery(name="api_key", auto_error=False)
    app = Faster()

    @app.get("/secure")
    async def secure(key: str | None = Depends(api_key)):
        return {"key": key}

    client = TestClient(app)
    resp = client.get("/secure")
    assert resp.status_code == 200
    assert resp.json()["key"] is None


def test_api_key_cookie_missing_auto_error_false():
    api_key = APIKeyCookie(name="session", auto_error=False)
    app = Faster()

    @app.get("/secure")
    async def secure(key: str | None = Depends(api_key)):
        return {"key": key}

    client = TestClient(app)
    resp = client.get("/secure")
    assert resp.status_code == 200
    assert resp.json()["key"] is None


def test_api_key_header_missing_auto_error_true():
    api_key = APIKeyHeader(name="X-API-Key", auto_error=True)
    app = Faster()

    @app.get("/secure")
    async def secure(key: str = Depends(api_key)):
        return {"key": key}

    client = TestClient(app)
    resp = client.get("/secure")
    assert resp.status_code == 403


def test_api_key_query_missing_auto_error_true():
    api_key = APIKeyQuery(name="api_key", auto_error=True)
    app = Faster()

    @app.get("/secure")
    async def secure(key: str = Depends(api_key)):
        return {"key": key}

    client = TestClient(app)
    resp = client.get("/secure")
    assert resp.status_code == 403


def test_api_key_cookie_missing_auto_error_true():
    api_key = APIKeyCookie(name="session", auto_error=True)
    app = Faster()

    @app.get("/secure")
    async def secure(key: str = Depends(api_key)):
        return {"key": key}

    client = TestClient(app)
    resp = client.get("/secure")
    assert resp.status_code == 403


def test_oauth2_bearer_no_auto_error_returns_none():
    oauth2 = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)
    app = Faster()

    @app.get("/optional")
    async def optional(token: str | None = Depends(oauth2)):
        return {"authenticated": token is not None}

    client = TestClient(app)
    resp = client.get("/optional")
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is False
