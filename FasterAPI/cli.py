"""FasterAPI command-line interface.

Commands
--------
fasterapi version             Print package version (same as ``get_version()``).
fasterapi run   <app>        Run with uvicorn (production mode).
fasterapi dev   <app>        Run with auto-reload (development mode).
fasterapi new   <name>       Scaffold a new FasterAPI project.
fasterapi migrate-from-fastapi <path>
                             Rewrite fastapi imports to FasterAPI in a file or directory.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    result: int = args.func(args)
    return result


# ---------------------------------------------------------------------------
#  Sub-command: run
# ---------------------------------------------------------------------------


def _cmd_run(args: argparse.Namespace) -> int:
    """Run the app with uvicorn in production mode."""
    cmd = _build_uvicorn_cmd(args, reload=False)
    return subprocess.call(cmd)


# ---------------------------------------------------------------------------
#  Sub-command: dev
# ---------------------------------------------------------------------------


def _cmd_dev(args: argparse.Namespace) -> int:
    """Run the app with uvicorn in development (auto-reload) mode."""
    cmd = _build_uvicorn_cmd(args, reload=True)
    return subprocess.call(cmd)


def _build_uvicorn_cmd(args: argparse.Namespace, *, reload: bool) -> list[str]:
    app_ref = args.app
    # Auto-detect if bare module name given (no colon) — look for 'app' object
    if ":" not in app_ref:
        app_ref = f"{app_ref}:app"

    cmd: list[str] = [
        sys.executable,
        "-m",
        "uvicorn",
        app_ref,
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if reload:
        cmd.append("--reload")
    else:
        cmd += ["--workers", str(args.workers)]

    if args.log_level:
        cmd += ["--log-level", args.log_level]

    return cmd


# ---------------------------------------------------------------------------
#  Sub-command: new
# ---------------------------------------------------------------------------


def _cmd_new(args: argparse.Namespace) -> int:
    """Scaffold a new FasterAPI project."""
    name: str = args.name
    dest = Path(name)

    if dest.exists():
        print(f"error: directory '{name}' already exists", file=sys.stderr)
        return 1

    dest.mkdir(parents=True)
    (dest / "app").mkdir()

    _write(dest / "app" / "__init__.py", "")
    _write(dest / "app" / "main.py", _MAIN_PY.format(name=name))
    _write(dest / "app" / "routers" / "__init__.py", "")
    _write(dest / "app" / "routers" / "items.py", _ITEMS_ROUTER_PY)
    _write(dest / "app" / "models.py", _MODELS_PY)
    _write(dest / "pyproject.toml", _PYPROJECT_TOML.format(name=name))
    _write(
        dest / "README.md",
        f"# {name}\n\nA FasterAPI application.\n\n## Run\n\n```bash\npip install -e .\nfasterapi dev app.main\n```\n",
    )
    _write(dest / ".gitignore", _GITIGNORE)
    _write(dest / ".env", "# Environment variables\nDEBUG=true\n")
    _write(dest / "Dockerfile", _DOCKERFILE.format(name=name))

    print(f"Created project '{name}'. Get started:\n")
    print(f"  cd {name}")
    print("  pip install -e .")
    print("  fasterapi dev app.main\n")
    return 0


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip())


def _cmd_version(_args: argparse.Namespace) -> int:
    from ._version import get_version

    print(get_version())
    return 0


# ---------------------------------------------------------------------------
#  Sub-command: migrate-from-fastapi
# ---------------------------------------------------------------------------


def _cmd_migrate(args: argparse.Namespace) -> int:
    """Rewrite fastapi imports to FasterAPI in a file or directory tree."""
    target = Path(args.path)
    if not target.exists():
        print(f"error: '{args.path}' does not exist", file=sys.stderr)
        return 1

    files = list(target.rglob("*.py")) if target.is_dir() else [target]
    changed = 0
    for f in files:
        if _migrate_file(f, dry_run=args.dry_run):
            changed += 1
            verb = "would rewrite" if args.dry_run else "rewritten"
            print(f"  {verb}: {f}")

    if args.dry_run:
        print(f"\nDry run: {changed} file(s) would be changed. Re-run without --dry-run to apply.")
    else:
        print(f"\nDone: {changed} file(s) rewritten.")
    return 0


# Substitution rules applied in order
_MIGRATION_RULES: list[tuple[str, str]] = [
    # Import rewriting — most specific first
    (r"from fastapi\.testclient import TestClient", "from FasterAPI.testclient import TestClient"),
    (r"from fastapi\.security import", "from FasterAPI.security import"),
    (r"from fastapi\.middleware\.cors import CORSMiddleware", "from FasterAPI.middleware import CORSMiddleware"),
    (r"from fastapi\.middleware\.gzip import GZipMiddleware", "from FasterAPI.middleware import GZipMiddleware"),
    (r"from fastapi\.middleware import", "from FasterAPI.middleware import"),
    (r"from fastapi\.staticfiles import StaticFiles", "from FasterAPI.staticfiles import StaticFiles"),
    (r"from fastapi\.templating import Jinja2Templates", "from FasterAPI.templating import Jinja2Templates"),
    (r"from fastapi\.responses import", "from FasterAPI.response import"),
    (r"from fastapi\.background import", "from FasterAPI.background import"),
    (r"from fastapi\.websockets import", "from FasterAPI.websocket import"),
    (r"from fastapi import APIRouter", "from FasterAPI import FasterRouter as APIRouter"),
    (r"from fastapi import FastAPI", "from FasterAPI import Faster as FastAPI"),
    (r"from fastapi import", "from FasterAPI import"),
    (r"import fastapi\b", "import FasterAPI"),
    # Class name rewriting
    (r"\bFastAPI\(\b", "Faster("),
    (r"\bAPIRouter\(\b", "FasterRouter("),
]


def _migrate_file(path: Path, *, dry_run: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    result = original
    for pattern, replacement in _MIGRATION_RULES:
        result = re.sub(pattern, replacement, result)
    if result == original:
        return False
    if not dry_run:
        path.write_text(result, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
#  Parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fasterapi",
        description="FasterAPI command-line interface",
    )
    sub = parser.add_subparsers(title="commands", metavar="<command>")

    # -- run --
    p_run = sub.add_parser("run", help="Run app with uvicorn (production)")
    _add_server_args(p_run)
    p_run.add_argument(
        "--workers",
        type=int,
        default=_default_workers(),
        metavar="N",
        help="Number of uvicorn worker processes (default: %(default)s)",
    )
    p_run.set_defaults(func=_cmd_run)

    # -- dev --
    p_dev = sub.add_parser("dev", help="Run app with auto-reload (development)")
    _add_server_args(p_dev)
    p_dev.set_defaults(func=_cmd_dev)

    # -- new --
    p_new = sub.add_parser("new", help="Scaffold a new FasterAPI project")
    p_new.add_argument("name", help="Project directory name")
    p_new.set_defaults(func=_cmd_new)

    # -- version --
    p_ver = sub.add_parser("version", help="Print installed faster-api-web version")
    p_ver.set_defaults(func=_cmd_version)

    # -- migrate-from-fastapi --
    p_mig = sub.add_parser("migrate-from-fastapi", help="Rewrite fastapi imports to FasterAPI")
    p_mig.add_argument("path", help="File or directory to migrate")
    p_mig.add_argument("--dry-run", action="store_true", help="Show what would change without writing files")
    p_mig.set_defaults(func=_cmd_migrate)

    return parser


def _add_server_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "app",
        nargs="?",
        default="main:app",
        help="App import string, e.g. main:app or mypackage.main (default: main:app)",
    )
    p.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    p.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        metavar="LEVEL",
        help="Log level (default: info)",
    )


def _default_workers() -> int:
    try:
        return (os.cpu_count() or 1) * 2 + 1
    except Exception:
        return 1


# ---------------------------------------------------------------------------
#  Project scaffold templates
# ---------------------------------------------------------------------------

_MAIN_PY = """\
from contextlib import asynccontextmanager

from FasterAPI import Faster

from .routers import items


@asynccontextmanager
async def lifespan(app: Faster):
    # Startup: initialise DB connections, caches, etc.
    yield
    # Shutdown: release resources


app = Faster(
    title="{name}",
    description="A FasterAPI application.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(items.router, prefix="/items", tags=["items"])


@app.get("/health", tags=["health"])
async def health():
    return {{"status": "ok"}}
"""

_ITEMS_ROUTER_PY = """\
import msgspec
from FasterAPI import FasterRouter, HTTPException

router = FasterRouter()


class Item(msgspec.Struct):
    id: int
    name: str
    price: float = 0.0


_DB: dict[int, Item] = {}
_NEXT_ID = 1


@router.get("/", response_model=list[Item])
async def list_items():
    return list(_DB.values())


@router.get("/{item_id}", response_model=Item)
async def get_item(item_id: int):
    item = _DB.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("/", response_model=Item, status_code=201)
async def create_item(body: Item):
    global _NEXT_ID
    item = Item(id=_NEXT_ID, name=body.name, price=body.price)
    _DB[_NEXT_ID] = item
    _NEXT_ID += 1
    return item


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: int):
    if item_id not in _DB:
        raise HTTPException(status_code=404, detail="Item not found")
    del _DB[item_id]
"""

_MODELS_PY = '''\
"""Shared data models for the application."""
import msgspec


class ErrorDetail(msgspec.Struct):
    detail: str
'''

_PYPROJECT_TOML = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "faster-api-web[all]>=0.1.0",
]

[project.optional-dependencies]
dev = [
    "httpx",
    "pytest",
    "pytest-asyncio",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["app"]
"""

_GITIGNORE = """\
__pycache__/
*.pyc
*.pyo
.venv/
.env
dist/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
"""

_DOCKERFILE = """\
FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[all]"
COPY app/ app/

RUN useradd -r -u 1001 appuser
USER appuser
EXPOSE 8000
CMD ["fasterapi", "run", "app.main", "--host", "0.0.0.0"]
"""
