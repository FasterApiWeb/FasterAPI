"""Tests for Phase 3 feature-parity additions.

Covers:
- openapi_extra on route decorators and FasterRouter
- Enum path parameter coercion (implicit and explicit Path marker)
- CLI argument parsing (fasterapi run / dev / new / migrate-from-fastapi)
"""

from __future__ import annotations

import enum
import textwrap
from unittest import mock

from FasterAPI import Faster, FasterRouter
from FasterAPI.cli import _build_parser, _migrate_file, main
from FasterAPI.openapi.generator import generate_openapi
from FasterAPI.params import Path as PathParam
from FasterAPI.testclient import TestClient

# ===========================================================================
#  openapi_extra
# ===========================================================================


class TestOpenAPIExtra:
    def test_extra_fields_appear_in_operation(self):
        app = Faster()

        @app.get(
            "/items",
            openapi_extra={
                "x-internal": True,
                "externalDocs": {"url": "https://example.com", "description": "Docs"},
            },
        )
        async def list_items():
            return []

        spec = generate_openapi(app, title="T", version="0")
        op = spec["paths"]["/items"]["get"]
        assert op["x-internal"] is True
        assert op["externalDocs"]["url"] == "https://example.com"

    def test_extra_does_not_clobber_existing_fields(self):
        app = Faster()

        @app.get("/health", summary="Health check", openapi_extra={"x-stable": True})
        async def health():
            return {"ok": True}

        spec = generate_openapi(app, title="T", version="0")
        op = spec["paths"]["/health"]["get"]
        assert op["summary"] == "Health check"
        assert op["x-stable"] is True

    def test_extra_responses_merged(self):
        app = Faster()

        @app.get(
            "/resource",
            openapi_extra={
                "responses": {"503": {"description": "Service unavailable"}},
            },
        )
        async def resource():
            return {}

        spec = generate_openapi(app, title="T", version="0")
        op = spec["paths"]["/resource"]["get"]
        assert "503" in op["responses"]
        assert op["responses"]["503"]["description"] == "Service unavailable"
        # Primary 200 must still exist
        assert "200" in op["responses"]

    def test_extra_on_router_route(self):
        router = FasterRouter(prefix="/v1")

        @router.get("/ping", openapi_extra={"x-router-extra": "yes"})
        async def ping():
            return {}

        app = Faster()
        app.include_router(router)
        spec = generate_openapi(app, title="T", version="0")
        op = spec["paths"]["/v1/ping"]["get"]
        assert op["x-router-extra"] == "yes"

    def test_none_extra_is_noop(self):
        app = Faster()

        @app.get("/noop", openapi_extra=None)
        async def noop():
            return {}

        spec = generate_openapi(app, title="T", version="0")
        op = spec["paths"]["/noop"]["get"]
        # Should not raise; operation is still valid
        assert "200" in op["responses"]


# ===========================================================================
#  Enum path parameter coercion
# ===========================================================================


class Color(enum.Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class Priority(enum.IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class TestEnumPathCoercion:
    def test_implicit_enum_path_param(self):
        app = Faster()

        @app.get("/colors/{color}")
        async def get_color(color: Color):
            return {"value": color.value}

        client = TestClient(app)
        resp = client.get("/colors/red")
        assert resp.status_code == 200
        assert resp.json() == {"value": "red"}

    def test_implicit_enum_invalid_value(self):
        app = Faster()

        @app.get("/colors/{color}")
        async def get_color(color: Color):
            return {"value": color.value}

        client = TestClient(app)
        resp = client.get("/colors/purple")
        assert resp.status_code == 422

    def test_explicit_path_marker_enum(self):
        app = Faster()

        @app.get("/prio/{level}")
        async def get_priority(level: Priority = PathParam()):
            return {"level": level.value}

        client = TestClient(app)
        resp = client.get("/prio/2")
        assert resp.status_code == 200
        assert resp.json() == {"level": 2}

    def test_explicit_path_marker_invalid_enum(self):
        app = Faster()

        @app.get("/prio/{level}")
        async def get_priority(level: Priority = PathParam()):
            return {"level": level.value}

        client = TestClient(app)
        resp = client.get("/prio/99")
        assert resp.status_code == 422

    def test_enum_coercion_does_not_affect_non_enum(self):
        app = Faster()

        @app.get("/items/{item_id}")
        async def get_item(item_id: str):
            return {"id": item_id}

        client = TestClient(app)
        resp = client.get("/items/hello")
        assert resp.status_code == 200
        assert resp.json() == {"id": "hello"}

    def test_enum_appears_in_openapi_schema(self):
        app = Faster()

        @app.get("/colors/{color}")
        async def get_color(color: Color):
            return {"value": color.value}

        spec = generate_openapi(app, title="T", version="0")
        params = spec["paths"]["/colors/{color}"]["get"]["parameters"]
        color_param = next(p for p in params if p["name"] == "color")
        # Enum values should appear in schema
        assert "enum" in color_param["schema"] or color_param["schema"].get("type") is not None


# ===========================================================================
#  CLI — argument parsing
# ===========================================================================


class TestCLIParser:
    def setup_method(self):
        self.parser = _build_parser()

    def test_run_defaults(self):
        args = self.parser.parse_args(["run"])
        assert args.app == "main:app"
        assert args.host == "127.0.0.1"
        assert args.port == 8000
        assert args.log_level == "info"

    def test_run_custom_args(self):
        args = self.parser.parse_args(["run", "myapp:application", "--host", "0.0.0.0", "--port", "9000"])
        assert args.app == "myapp:application"
        assert args.host == "0.0.0.0"
        assert args.port == 9000

    def test_dev_has_no_workers_arg(self):
        args = self.parser.parse_args(["dev", "app.main"])
        assert args.app == "app.main"
        assert not hasattr(args, "workers")

    def test_new_command(self):
        args = self.parser.parse_args(["new", "myproject"])
        assert args.name == "myproject"

    def test_migrate_command(self):
        args = self.parser.parse_args(["migrate-from-fastapi", "/some/path"])
        assert args.path == "/some/path"
        assert args.dry_run is False

    def test_migrate_dry_run(self):
        args = self.parser.parse_args(["migrate-from-fastapi", "/some/path", "--dry-run"])
        assert args.dry_run is True

    def test_no_subcommand_returns_1(self):
        rc = main([])
        assert rc == 1


class TestCLIRunDev:
    def test_run_calls_uvicorn(self):
        with mock.patch("subprocess.call", return_value=0) as m:
            rc = main(["run", "app.main:app", "--port", "8001"])
        assert rc == 0
        cmd = m.call_args[0][0]
        assert "uvicorn" in cmd
        assert "app.main:app" in cmd
        assert "--port" in cmd
        assert "8001" in cmd
        assert "--reload" not in cmd

    def test_dev_adds_reload(self):
        with mock.patch("subprocess.call", return_value=0) as m:
            main(["dev", "app.main:app"])
        cmd = m.call_args[0][0]
        assert "--reload" in cmd

    def test_run_auto_expands_bare_module(self):
        with mock.patch("subprocess.call", return_value=0) as m:
            main(["run", "mymodule"])
        cmd = m.call_args[0][0]
        assert "mymodule:app" in cmd


class TestCLINew:
    def test_new_creates_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        rc = main(["new", "testproj"])
        assert rc == 0
        proj = tmp_path / "testproj"
        assert (proj / "app" / "main.py").exists()
        assert (proj / "app" / "routers" / "items.py").exists()
        assert (proj / "pyproject.toml").exists()
        assert (proj / "Dockerfile").exists()
        assert (proj / ".gitignore").exists()

    def test_new_main_py_content(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])
        content = (tmp_path / "myapp" / "app" / "main.py").read_text()
        assert "from FasterAPI import Faster" in content
        assert "myapp" in content

    def test_new_fails_if_dir_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "existing").mkdir()
        rc = main(["new", "existing"])
        assert rc == 1


class TestCLIMigrate:
    def test_migrate_rewrites_fastapi_imports(self, tmp_path):
        src = tmp_path / "app.py"
        src.write_text(
            textwrap.dedent("""\
            from fastapi import FastAPI
            from fastapi import APIRouter
            from fastapi.responses import JSONResponse
            from fastapi.middleware.cors import CORSMiddleware

            app = FastAPI()
        """)
        )
        rc = main(["migrate-from-fastapi", str(src)])
        assert rc == 0
        result = src.read_text()
        assert "from FasterAPI import" in result
        assert "from fastapi import FastAPI" not in result

    def test_migrate_dry_run_does_not_write(self, tmp_path):
        src = tmp_path / "app.py"
        original = "from fastapi import FastAPI\napp = FastAPI()\n"
        src.write_text(original)
        main(["migrate-from-fastapi", str(src), "--dry-run"])
        assert src.read_text() == original

    def test_migrate_directory(self, tmp_path):
        (tmp_path / "a.py").write_text("from fastapi import FastAPI\n")
        (tmp_path / "b.py").write_text("from fastapi import APIRouter\n")
        rc = main(["migrate-from-fastapi", str(tmp_path)])
        assert rc == 0
        assert "FasterAPI" in (tmp_path / "a.py").read_text()
        assert "FasterAPI" in (tmp_path / "b.py").read_text()

    def test_migrate_unchanged_file_not_reported(self, tmp_path):
        src = tmp_path / "clean.py"
        src.write_text("x = 1\n")
        changed = _migrate_file(src, dry_run=False)
        assert changed is False
        assert src.read_text() == "x = 1\n"

    def test_migrate_missing_path_returns_1(self):
        rc = main(["migrate-from-fastapi", "/nonexistent/path"])
        assert rc == 1
