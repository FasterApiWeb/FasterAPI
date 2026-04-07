from __future__ import annotations

import inspect
import typing
from typing import Any, Callable

import msgspec

from .background import BackgroundTasks
from .concurrency import is_coroutine
from .datastructures import UploadFile
from .exceptions import HTTPException, RequestValidationError
from .params import Body, Cookie, File, Form, Header, Path, Query, _MISSING
from .request import Request


class Depends:
    __slots__ = ("dependency", "use_cache")

    def __init__(self, dependency: Callable, *, use_cache: bool = True) -> None:
        self.dependency = dependency
        self.use_cache = use_cache

    def __repr__(self) -> str:
        return f"Depends({self.dependency.__name__})"


async def _resolve_handler(
    handler: Callable,
    request: Request,
    path_params: dict[str, str],
) -> tuple[Any, BackgroundTasks | None]:
    cache: dict[Callable, Any] = {}
    bg_tasks = BackgroundTasks()
    kwargs = await _resolve_params(handler, request, path_params, cache, bg_tasks)

    if is_coroutine(handler):
        result = await handler(**kwargs)
    else:
        result = handler(**kwargs)

    return result, bg_tasks if bg_tasks._tasks else None


async def _resolve_params(
    func: Callable,
    request: Request,
    path_params: dict[str, str],
    cache: dict[Callable, Any],
    bg_tasks: BackgroundTasks,
) -> dict[str, Any]:
    sig = inspect.signature(func)
    try:
        type_hints = typing.get_type_hints(func)
    except Exception:
        type_hints = {}
    kwargs: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        annotation = type_hints.get(name, param.annotation)
        default = param.default

        # BackgroundTasks injection
        if annotation is BackgroundTasks:
            kwargs[name] = bg_tasks
            continue

        # Request injection
        if annotation is Request:
            kwargs[name] = request
            continue

        # Depends() — recursive dependency resolution
        if isinstance(default, Depends):
            kwargs[name] = await _resolve_dependency(
                default, request, path_params, cache, bg_tasks,
            )
            continue

        # msgspec.Struct subclass — decode body
        if _is_struct_type(annotation):
            kwargs[name] = await _resolve_struct(annotation, request, default)
            continue

        # Path()
        if isinstance(default, Path):
            kwargs[name] = _resolve_path(name, path_params, default)
            continue

        # Query()
        if isinstance(default, Query):
            kwargs[name] = _resolve_query(name, request, default)
            continue

        # Header()
        if isinstance(default, Header):
            kwargs[name] = _resolve_header(name, request, default)
            continue

        # Cookie()
        if isinstance(default, Cookie):
            kwargs[name] = _resolve_cookie(name, request, default)
            continue

        # File() — UploadFile from multipart form data
        if isinstance(default, File) or (
            _is_upload_file_type(annotation) and not isinstance(default, (Path, Query, Header, Cookie, Body, Form))
        ):
            kwargs[name] = await _resolve_file(name, request)
            continue

        # Form() — scalar form field
        if isinstance(default, Form):
            kwargs[name] = await _resolve_form_field(name, request, default)
            continue

        # Body() explicit marker
        if isinstance(default, Body):
            kwargs[name] = await _resolve_body(request, default)
            continue

        # Unannotated param with no special default — try path_params, then query
        if name in path_params:
            kwargs[name] = path_params[name]
        elif default is not inspect.Parameter.empty:
            kwargs[name] = default

    return kwargs


async def _resolve_dependency(
    dep: Depends,
    request: Request,
    path_params: dict[str, str],
    cache: dict[Callable, Any],
    bg_tasks: BackgroundTasks,
) -> Any:
    func = dep.dependency

    if dep.use_cache and func in cache:
        return cache[func]

    dep_kwargs = await _resolve_params(func, request, path_params, cache, bg_tasks)

    if is_coroutine(func):
        result = await func(**dep_kwargs)
    else:
        result = func(**dep_kwargs)

    if dep.use_cache:
        cache[func] = result
    return result


def _is_struct_type(annotation: Any) -> bool:
    return (
        annotation is not inspect.Parameter.empty
        and isinstance(annotation, type)
        and issubclass(annotation, msgspec.Struct)
    )


async def _resolve_struct(
    struct_type: type, request: Request, default: Any,
) -> Any:
    try:
        raw = await request._read_body()
        return msgspec.json.decode(raw, type=struct_type)
    except (msgspec.DecodeError, msgspec.ValidationError) as exc:
        if default is not inspect.Parameter.empty:
            return default
        raise RequestValidationError(
            [{"loc": ["body"], "msg": str(exc), "type": "value_error.msgspec"}],
        ) from exc


def _resolve_path(
    name: str, path_params: dict[str, str], marker: Path,
) -> Any:
    if name in path_params:
        return path_params[name]
    if marker.default is not _MISSING:
        return marker.default
    raise RequestValidationError(
        [{"loc": ["path", name], "msg": "Missing required path parameter", "type": "value_error.missing"}],
    )


def _resolve_query(
    name: str, request: Request, marker: Query,
) -> Any:
    key = marker.alias or name
    value = request.query_params.get(key)
    if value is not None:
        return value
    return marker.default


def _resolve_header(
    name: str, request: Request, marker: Header,
) -> Any:
    if marker.alias:
        key = marker.alias.lower()
    elif marker.convert_underscores:
        key = name.replace("_", "-")
    else:
        key = name
    value = request.headers.get(key)
    if value is not None:
        return value
    return marker.default


def _resolve_cookie(
    name: str, request: Request, marker: Cookie,
) -> Any:
    value = request.cookies.get(name)
    if value is not None:
        return value
    return marker.default


async def _resolve_file(name: str, request: Request) -> UploadFile:
    form_data = await request.form()
    value = form_data.get(name)
    if isinstance(value, UploadFile):
        return value
    raise RequestValidationError(
        [{"loc": ["body", name], "msg": "Expected an uploaded file", "type": "value_error.missing"}],
    )


async def _resolve_form_field(
    name: str, request: Request, marker: Form,
) -> Any:
    form_data = await request.form()
    value = form_data.get(name)
    if value is not None:
        return value
    if marker.default is not _MISSING:
        return marker.default
    return None


def _is_upload_file_type(annotation: Any) -> bool:
    return (
        annotation is not inspect.Parameter.empty
        and isinstance(annotation, type)
        and issubclass(annotation, UploadFile)
    )


async def _resolve_body(request: Request, marker: Body) -> Any:
    try:
        return await request.json()
    except Exception as exc:
        if marker.default is not _MISSING:
            return marker.default
        raise RequestValidationError(
            [{"loc": ["body"], "msg": str(exc), "type": "value_error.missing"}],
        ) from exc
