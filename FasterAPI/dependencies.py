"""Dependency injection and handler resolution for FasterAPI.

The key optimization here is _compile_handler(): instead of calling
inspect.signature() and typing.get_type_hints() on every request,
we introspect once at route-registration time and produce a compact
list of (_ParamSpec, ...) tuples that the hot-path resolver iterates.
"""

from __future__ import annotations

import dataclasses
import inspect
import typing
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Any, get_args, get_origin

import msgspec

from .background import BackgroundTasks
from .concurrency import is_coroutine
from .datastructures import UploadFile
from .exceptions import RequestValidationError
from .params import _MISSING, Body, Cookie, File, Form, Header, Path, Query
from .request import Request

__all__ = ["Depends", "compile_handler", "_resolve_handler"]

# ---------------------------------------------------------------------------
#  Depends marker
# ---------------------------------------------------------------------------


class Depends:
    """Declare a dependency to be resolved and injected into a route handler."""

    __slots__ = ("dependency", "use_cache")

    def __init__(self, dependency: Callable[..., Any] | None = None, *, use_cache: bool = True) -> None:
        self.dependency = dependency
        self.use_cache = use_cache

    def __repr__(self) -> str:
        name = self.dependency.__name__ if self.dependency else "..."
        return f"Depends({name})"


# ---------------------------------------------------------------------------
#  Param kind enum (avoids isinstance chains in the hot loop)
# ---------------------------------------------------------------------------

_KIND_REQUEST = 0
_KIND_BG_TASKS = 1
_KIND_DEPENDS = 2
_KIND_STRUCT = 3
_KIND_PATH = 4
_KIND_QUERY = 5
_KIND_HEADER = 6
_KIND_COOKIE = 7
_KIND_FILE = 8
_KIND_FORM = 9
_KIND_BODY = 10
_KIND_FALLBACK = 11
_KIND_DATACLASS = 12
_KIND_FORM_BODY = 13  # OAuth2PasswordRequestForm and similar class-based form deps


class _ParamSpec:
    """Pre-computed metadata for a single handler parameter."""

    __slots__ = ("name", "kind", "annotation", "default", "marker")

    def __init__(
        self,
        name: str,
        kind: int,
        annotation: Any,
        default: Any,
        marker: Any,
    ) -> None:
        self.name = name
        self.kind = kind
        self.annotation = annotation
        self.default = default
        self.marker = marker


# ---------------------------------------------------------------------------
#  Annotated unwrapping helpers
# ---------------------------------------------------------------------------


def _unwrap_annotated(annotation: Any, default: Any) -> tuple[Any, Any]:
    """If *annotation* is Annotated[T, marker, ...], return (T, first_marker).

    Supports PEP 593 style:  Annotated[str, Depends(get_token)]
                               Annotated[str, Query(alias="q")]
    """
    if get_origin(annotation) is not Annotated:
        return annotation, default

    args = get_args(annotation)
    inner_type = args[0]
    # Walk metadata left-to-right; use the first recognised marker.
    _marker_types = (Depends, Path, Query, Header, Cookie, Body, File, Form)
    for meta in args[1:]:
        if isinstance(meta, _marker_types):
            return inner_type, meta
    return inner_type, default


# ---------------------------------------------------------------------------
#  Compile handler (called once at route registration)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=512)
def compile_handler(func: Callable[..., Any]) -> tuple[tuple[_ParamSpec, ...], bool]:
    """Introspect *func* once and return a tuple of _ParamSpec plus is-async flag."""
    # For class-based dependencies (e.g. OAuth2PasswordRequestForm), inspect __init__
    if inspect.isclass(func):
        sig = inspect.signature(func)
        try:
            type_hints = typing.get_type_hints(func.__init__, include_extras=True)
        except Exception:
            type_hints = {}
        type_hints.pop("return", None)
        is_async = False
    elif callable(func) and not inspect.isfunction(func) and not inspect.isbuiltin(func):
        # Callable instance (e.g. OAuth2PasswordBearer instance) — use the class __call__
        sig = inspect.signature(func)
        call_method = inspect.getattr_static(type(func), "__call__", None)
        try:
            type_hints = typing.get_type_hints(call_method, include_extras=True) if call_method else {}
        except Exception:
            type_hints = {}
        is_async = is_coroutine(call_method) if call_method else False
    else:
        sig = inspect.signature(func)
        try:
            type_hints = typing.get_type_hints(func, include_extras=True)
        except Exception:
            type_hints = {}
        is_async = is_coroutine(func)

    specs: list[_ParamSpec] = []
    for name, param in sig.parameters.items():
        raw_annotation = type_hints.get(name, param.annotation)
        raw_default = param.default

        # Unwrap Annotated[T, marker] — PEP 593 support
        annotation, default = _unwrap_annotated(raw_annotation, raw_default)

        if annotation is BackgroundTasks:
            specs.append(_ParamSpec(name, _KIND_BG_TASKS, annotation, default, None))
        elif annotation is Request:
            specs.append(_ParamSpec(name, _KIND_REQUEST, annotation, default, None))
        elif isinstance(default, Depends):
            # Annotated[str, Depends(fn)] or foo: str = Depends(fn)
            specs.append(_ParamSpec(name, _KIND_DEPENDS, annotation, default, default))
        elif _is_struct_type(annotation):
            specs.append(_ParamSpec(name, _KIND_STRUCT, annotation, default, None))
        elif _is_dataclass_type(annotation):
            specs.append(_ParamSpec(name, _KIND_DATACLASS, annotation, default, None))
        elif isinstance(default, Path):
            specs.append(_ParamSpec(name, _KIND_PATH, annotation, default, default))
        elif isinstance(default, Query):
            specs.append(_ParamSpec(name, _KIND_QUERY, annotation, default, default))
        elif isinstance(default, Header):
            specs.append(_ParamSpec(name, _KIND_HEADER, annotation, default, default))
        elif isinstance(default, Cookie):
            specs.append(_ParamSpec(name, _KIND_COOKIE, annotation, default, default))
        elif isinstance(default, File) or _is_upload_file_type(annotation):
            specs.append(_ParamSpec(name, _KIND_FILE, annotation, default, default))
        elif isinstance(default, Form):
            specs.append(_ParamSpec(name, _KIND_FORM, annotation, default, default))
        elif isinstance(default, Body):
            specs.append(_ParamSpec(name, _KIND_BODY, annotation, default, default))
        else:
            specs.append(_ParamSpec(name, _KIND_FALLBACK, annotation, default, None))

    return tuple(specs), is_async


# ---------------------------------------------------------------------------
#  Hot-path resolver (called on every request)
# ---------------------------------------------------------------------------


async def _resolve_handler(
    handler: Callable[..., Any],
    request: Request,
    path_params: dict[str, str],
    extra_deps: list[Depends] | None = None,
) -> tuple[Any, BackgroundTasks | None]:
    """Resolve dependencies, call handler, return (result, bg_tasks|None)."""
    specs, is_async = compile_handler(handler)
    cache: dict[Callable[..., Any], Any] = {}
    bg_tasks = BackgroundTasks()

    # Router-level dependencies resolved before handler params
    if extra_deps:
        for dep in extra_deps:
            await _resolve_dependency(dep, request, path_params, cache, bg_tasks)

    kwargs = await _resolve_from_specs(specs, request, path_params, cache, bg_tasks)

    result = await handler(**kwargs) if is_async else handler(**kwargs)
    return result, bg_tasks if bg_tasks._tasks else None


async def _resolve_from_specs(
    specs: tuple[_ParamSpec, ...],
    request: Request,
    path_params: dict[str, str],
    cache: dict[Callable[..., Any], Any],
    bg_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Build kwargs dict from pre-compiled param specs — no introspection."""
    kwargs: dict[str, Any] = {}

    for spec in specs:
        kind = spec.kind

        if kind == _KIND_REQUEST:
            kwargs[spec.name] = request
        elif kind == _KIND_BG_TASKS:
            kwargs[spec.name] = bg_tasks
        elif kind == _KIND_DEPENDS:
            kwargs[spec.name] = await _resolve_dependency(
                spec.marker,
                request,
                path_params,
                cache,
                bg_tasks,
            )
        elif kind == _KIND_STRUCT:
            kwargs[spec.name] = await _resolve_struct(
                spec.annotation,
                request,
                spec.default,
            )
        elif kind == _KIND_DATACLASS:
            kwargs[spec.name] = await _resolve_dataclass(
                spec.annotation,
                request,
                spec.default,
            )
        elif kind == _KIND_PATH:
            kwargs[spec.name] = _resolve_path(spec.name, path_params, spec.marker)
        elif kind == _KIND_QUERY:
            kwargs[spec.name] = _resolve_query(spec.name, request, spec.marker)
        elif kind == _KIND_HEADER:
            kwargs[spec.name] = _resolve_header(spec.name, request, spec.marker)
        elif kind == _KIND_COOKIE:
            kwargs[spec.name] = _resolve_cookie(spec.name, request, spec.marker)
        elif kind == _KIND_FILE:
            kwargs[spec.name] = await _resolve_file(spec.name, request)
        elif kind == _KIND_FORM:
            kwargs[spec.name] = await _resolve_form_field(
                spec.name,
                request,
                spec.marker,
            )
        elif kind == _KIND_BODY:
            kwargs[spec.name] = await _resolve_body(request, spec.marker)
        else:
            if spec.name in path_params:
                kwargs[spec.name] = path_params[spec.name]
            elif spec.default is not inspect.Parameter.empty:
                kwargs[spec.name] = spec.default

    return kwargs


# ---------------------------------------------------------------------------
#  Dependency resolution
# ---------------------------------------------------------------------------


async def _resolve_dependency(
    dep: Depends,
    request: Request,
    path_params: dict[str, str],
    cache: dict[Callable[..., Any], Any],
    bg_tasks: BackgroundTasks,
) -> Any:
    func = dep.dependency
    if func is None:
        return None

    if dep.use_cache and func in cache:
        return cache[func]

    # Special case: OAuth2PasswordRequestForm and similar class-based form-body deps
    if inspect.isclass(func) and hasattr(func, "from_request"):
        result = await func.from_request(request)
        if dep.use_cache:
            cache[func] = result
        return result

    specs, is_async = compile_handler(func)
    dep_kwargs = await _resolve_from_specs(specs, request, path_params, cache, bg_tasks)

    if inspect.isclass(func):
        # Instantiate the class synchronously
        result = func(**dep_kwargs)
    elif is_async:
        result = await func(**dep_kwargs)
    else:
        result = func(**dep_kwargs)

    if dep.use_cache:
        cache[func] = result
    return result


# ---------------------------------------------------------------------------
#  Individual param resolvers (kept lean)
# ---------------------------------------------------------------------------


def _is_struct_type(annotation: Any) -> bool:
    return (
        annotation is not inspect.Parameter.empty
        and isinstance(annotation, type)
        and issubclass(annotation, msgspec.Struct)
    )


def _is_dataclass_type(annotation: Any) -> bool:
    return (
        annotation is not inspect.Parameter.empty
        and isinstance(annotation, type)
        and dataclasses.is_dataclass(annotation)
    )


def _is_upload_file_type(annotation: Any) -> bool:
    return (
        annotation is not inspect.Parameter.empty
        and isinstance(annotation, type)
        and issubclass(annotation, UploadFile)
    )


async def _resolve_struct(
    struct_type: type,
    request: Request,
    default: Any,
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


async def _resolve_dataclass(
    dc_type: type,
    request: Request,
    default: Any,
) -> Any:
    """Resolve a standard @dataclass from the JSON request body."""
    try:
        raw = await request._read_body()
        data = msgspec.json.decode(raw, type=dict)
        fields = {f.name for f in dataclasses.fields(dc_type)}
        filtered = {k: v for k, v in data.items() if k in fields}
        return dc_type(**filtered)
    except Exception as exc:
        if default is not inspect.Parameter.empty:
            return default
        raise RequestValidationError(
            [{"loc": ["body"], "msg": str(exc), "type": "value_error.dataclass"}],
        ) from exc


def _resolve_path(name: str, path_params: dict[str, str], marker: Path) -> Any:
    if name in path_params:
        return path_params[name]
    if marker.default is not _MISSING:
        return marker.default
    raise RequestValidationError(
        [{"loc": ["path", name], "msg": "Missing required path parameter", "type": "value_error.missing"}],
    )


def _resolve_query(name: str, request: Request, marker: Query) -> Any:
    key = marker.alias or name
    value = request.query_params.get(key)
    return value if value is not None else marker.default


def _resolve_header(name: str, request: Request, marker: Header) -> Any:
    if marker.alias:
        key = marker.alias.lower()
    elif marker.convert_underscores:
        key = name.replace("_", "-")
    else:
        key = name
    value = request.headers.get(key)
    return value if value is not None else marker.default


def _resolve_cookie(name: str, request: Request, marker: Cookie) -> Any:
    value = request.cookies.get(name)
    return value if value is not None else marker.default


async def _resolve_file(name: str, request: Request) -> UploadFile:
    form_data = await request.form()
    value = form_data.get(name)
    if isinstance(value, UploadFile):
        return value
    raise RequestValidationError(
        [{"loc": ["body", name], "msg": "Expected an uploaded file", "type": "value_error.missing"}],
    )


async def _resolve_form_field(name: str, request: Request, marker: Form) -> Any:
    form_data = await request.form()
    value = form_data.get(name)
    if value is not None:
        return value
    if marker.default is not _MISSING:
        return marker.default
    return None


async def _resolve_body(request: Request, marker: Body) -> Any:
    try:
        return await request.json()
    except Exception as exc:
        if marker.default is not _MISSING:
            return marker.default
        raise RequestValidationError(
            [{"loc": ["body"], "msg": str(exc), "type": "value_error.missing"}],
        ) from exc
