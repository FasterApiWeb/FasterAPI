from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import inspect
import re
import types
import typing
import uuid
from collections.abc import Callable
from typing import Annotated, Any, Union, get_args, get_origin

import msgspec

from .._version import get_version
from ..params import Body, Cookie, Header, Path, Query


def generate_openapi(
    app: Any,
    *,
    title: str = "FasterAPI",
    version: str | None = None,
    description: str = "",
    openapi_tags: list[dict[str, Any]] | None = None,
    terms_of_service: str | None = None,
    contact: dict[str, str] | None = None,
    license_info: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Generate an OpenAPI 3.0.3 spec dict from a Faster app instance."""
    if version is None:
        version = get_version()
    if hasattr(app, "_openapi_cache") and app._openapi_cache is not None:
        result: dict[str, Any] = app._openapi_cache
        return result

    schemas: dict[str, Any] = {}
    paths: dict[str, Any] = {}

    for route in app.routes:
        method = route["method"].lower()
        raw_path = route["path"]
        handler = route["handler"]
        openapi_path = raw_path

        operation = _build_operation(route, handler, schemas)
        paths.setdefault(openapi_path, {})[method] = operation

    info: dict[str, Any] = {"title": title, "version": version}
    if description:
        info["description"] = description
    if terms_of_service:
        info["termsOfService"] = terms_of_service
    if contact:
        info["contact"] = contact
    if license_info:
        info["license"] = license_info

    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": info,
        "paths": paths,
    }
    if openapi_tags:
        spec["tags"] = openapi_tags
    if schemas:
        spec["components"] = {"schemas": schemas}

    app._openapi_cache = spec
    return spec


def _build_operation(
    route: dict[str, Any],
    handler: Callable[..., Any],
    schemas: dict[str, Any],
) -> dict[str, Any]:
    operation: dict[str, Any] = {}

    tags = route.get("tags", [])
    if tags:
        operation["tags"] = tags

    summary = route.get("summary", "")
    if summary:
        operation["summary"] = summary
    else:
        operation["summary"] = handler.__name__.replace("_", " ").title()

    doc = inspect.getdoc(handler)
    if doc:
        operation["description"] = doc

    if route.get("deprecated", False):
        operation["deprecated"] = True

    operation["operationId"] = handler.__name__

    parameters, request_body = _extract_params(route, handler, schemas)
    if parameters:
        operation["parameters"] = parameters
    if request_body:
        operation["requestBody"] = request_body

    # Build responses dict
    status_code = str(route.get("status_code", 200))
    response_model = route.get("response_model")
    responses: dict[str, Any] = {}

    if response_model is not None:
        schema = _type_to_schema(response_model, schemas)
        responses[status_code] = {
            "description": "Successful Response",
            "content": {"application/json": {"schema": schema}},
        }
    else:
        responses[status_code] = {"description": "Successful Response"}

    # Merge additional responses declared via responses={404: {...}}
    extra_responses: dict[int | str, dict[str, Any]] | None = route.get("responses")
    if extra_responses:
        for code, resp_def in extra_responses.items():
            key = str(code)
            merged: dict[str, Any] = {"description": resp_def.get("description", "Response")}
            model = resp_def.get("model")
            if model is not None:
                extra_schema = _type_to_schema(model, schemas)
                merged["content"] = {"application/json": {"schema": extra_schema}}
            elif "content" in resp_def:
                merged["content"] = resp_def["content"]
            responses[key] = merged

    if parameters or request_body:
        responses.setdefault(
            "422",
            {
                "description": "Validation Error",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "detail": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "loc": {"type": "array", "items": {"type": "string"}},
                                            "msg": {"type": "string"},
                                            "type": {"type": "string"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        )

    operation["responses"] = responses
    return operation


def _extract_params(
    route: dict[str, Any],
    handler: Callable[..., Any],
    schemas: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    parameters: list[dict[str, Any]] = []
    request_body: dict[str, Any] | None = None

    path_param_names = set(re.findall(r"\{(\w+)\}", route["path"]))

    try:
        sig = inspect.signature(handler)
    except (ValueError, TypeError):
        return parameters, request_body

    try:
        hints = typing.get_type_hints(handler, include_extras=True)
    except Exception:
        hints = {}

    for name, param in sig.parameters.items():
        raw_annotation = hints.get(name, param.annotation)
        raw_default = param.default

        # Unwrap Annotated[T, marker]
        annotation, default = _unwrap_annotated_for_openapi(raw_annotation, raw_default)

        from ..request import Request as RequestClass

        if annotation is RequestClass:
            continue

        from ..dependencies import Depends

        if isinstance(default, Depends) or isinstance(raw_default, Depends):
            continue

        # Path parameter
        if isinstance(default, Path) or name in path_param_names:
            p: dict[str, Any] = {
                "name": name,
                "in": "path",
                "required": True,
                "schema": _annotation_to_schema(annotation, schemas),
            }
            desc = default.description if isinstance(default, Path) else ""
            if desc:
                p["description"] = desc
            parameters.append(p)
            continue

        # Query parameter
        if isinstance(default, Query):
            p = {
                "name": default.alias or name,
                "in": "query",
                "required": default.default is None and not _is_optional(annotation),
                "schema": _annotation_to_schema(annotation, schemas),
            }
            if default.description:
                p["description"] = default.description
            if default.default is not None:
                p["schema"]["default"] = default.default
            parameters.append(p)
            continue

        # Header parameter
        if isinstance(default, Header):
            header_name = default.alias or (name.replace("_", "-") if default.convert_underscores else name)
            p = {
                "name": header_name,
                "in": "header",
                "required": default.default is None,
                "schema": _annotation_to_schema(annotation, schemas),
            }
            if default.default is not None:
                p["schema"]["default"] = default.default
            parameters.append(p)
            continue

        # Cookie parameter
        if isinstance(default, Cookie):
            p = {
                "name": name,
                "in": "cookie",
                "required": default.default is None,
                "schema": _annotation_to_schema(annotation, schemas),
            }
            if default.default is not None:
                p["schema"]["default"] = default.default
            parameters.append(p)
            continue

        # Body / msgspec.Struct / dataclass
        if isinstance(default, Body) or _is_struct_type(annotation) or _is_dataclass_type(annotation):
            schema = _type_to_schema(annotation, schemas)
            request_body = {
                "required": True,
                "content": {"application/json": {"schema": schema}},
            }
            continue

    return parameters, request_body


def _unwrap_annotated_for_openapi(annotation: Any, default: Any) -> tuple[Any, Any]:
    if get_origin(annotation) is not Annotated:
        return annotation, default
    args = get_args(annotation)
    inner = args[0]
    _marker_types = (Path, Query, Header, Cookie, Body)
    for meta in args[1:]:
        if isinstance(meta, _marker_types):
            return inner, meta
    return inner, default


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


def _is_optional(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = get_args(annotation)
        return type(None) in args
    return False


def _annotation_to_schema(
    annotation: Any,
    schemas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}
    return _python_type_to_schema(annotation, schemas)


def _python_type_to_schema(
    tp: Any,
    schemas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tp is str:
        return {"type": "string"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if tp is bool:
        return {"type": "boolean"}
    if tp is datetime.datetime:
        return {"type": "string", "format": "date-time"}
    if tp is datetime.date:
        return {"type": "string", "format": "date"}
    if tp is datetime.time:
        return {"type": "string", "format": "time"}
    if tp is uuid.UUID:
        return {"type": "string", "format": "uuid"}
    if tp is decimal.Decimal:
        return {"type": "string", "format": "decimal"}

    # Enum
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        values = [m.value for m in tp]
        # Infer type from values
        if all(isinstance(v, int) for v in values):
            return {"type": "integer", "enum": values}
        return {"type": "string", "enum": values}

    # msgspec.Struct
    if _is_struct_type(tp):
        if schemas is not None:
            return _struct_to_ref(tp, schemas)
        return {"type": "object"}

    # dataclass
    if _is_dataclass_type(tp):
        if schemas is not None:
            return _dataclass_to_ref(tp, schemas)
        return {"type": "object"}

    origin = get_origin(tp)
    args = get_args(tp)

    # Optional[X] = Union[X, None] or X | None
    if origin is Union or origin is types.UnionType:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            schema = _python_type_to_schema(non_none[0], schemas)
            schema["nullable"] = True
            return schema
        return {"type": "string"}

    # list / List[T]
    if origin is list:
        if args:
            return {"type": "array", "items": _python_type_to_schema(args[0], schemas)}
        return {"type": "array", "items": {}}

    # dict / Dict[K, V]
    if origin is dict:
        dict_schema: dict[str, Any] = {"type": "object"}
        if args and len(args) == 2:
            dict_schema["additionalProperties"] = _python_type_to_schema(args[1], schemas)
        return dict_schema

    return {"type": "string"}


def _type_to_schema(
    tp: Any,
    schemas: dict[str, Any],
) -> dict[str, Any]:
    if tp is None or tp is inspect.Parameter.empty:
        return {"type": "string"}

    if _is_struct_type(tp):
        return _struct_to_ref(tp, schemas)

    if _is_dataclass_type(tp):
        return _dataclass_to_ref(tp, schemas)

    return _python_type_to_schema(tp, schemas)


def _struct_to_ref(
    struct_type: type,
    schemas: dict[str, Any],
) -> dict[str, Any]:
    name = struct_type.__name__
    if name not in schemas:
        schemas[name] = _struct_to_schema(struct_type, schemas)
    return {"$ref": f"#/components/schemas/{name}"}


def _dataclass_to_ref(
    dc_type: type,
    schemas: dict[str, Any],
) -> dict[str, Any]:
    name = dc_type.__name__
    if name not in schemas:
        schemas[name] = _dataclass_to_schema(dc_type, schemas)
    return {"$ref": f"#/components/schemas/{name}"}


def _struct_to_schema(
    struct_type: type,
    schemas: dict[str, Any],
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []

    hints = _get_struct_fields(struct_type)
    defaults = _get_struct_defaults(struct_type)

    for field_name, field_type in hints.items():
        prop = _type_to_schema(field_type, schemas)
        properties[field_name] = prop

        if field_name not in defaults and not _is_optional(field_type):
            required.append(field_name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    doc = struct_type.__doc__
    if doc and doc != msgspec.Struct.__doc__:
        doc = inspect.cleandoc(doc)
        if doc:
            schema["description"] = doc

    return schema


def _dataclass_to_schema(
    dc_type: type,
    schemas: dict[str, Any],
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []

    try:
        hints = typing.get_type_hints(dc_type)
    except Exception:
        hints = {f.name: f.type for f in dataclasses.fields(dc_type)}

    defaults = {
        f.name
        for f in dataclasses.fields(dc_type)
        if f.default is not dataclasses.MISSING or callable(f.default_factory)
    }

    for field_name, field_type in hints.items():
        prop = _type_to_schema(field_type, schemas)
        properties[field_name] = prop
        if field_name not in defaults and not _is_optional(field_type):
            required.append(field_name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required

    doc = inspect.getdoc(dc_type)
    if doc:
        schema["description"] = doc

    return schema


def _get_struct_fields(struct_type: type) -> dict[str, Any]:
    try:
        hints = typing.get_type_hints(struct_type)
    except Exception:
        hints = {}
        for cls in reversed(struct_type.__mro__):
            if hasattr(cls, "__annotations__"):
                hints.update(cls.__annotations__)
    hints.pop("__struct_fields__", None)
    hints.pop("__struct_config__", None)
    return hints


def _get_struct_defaults(struct_type: type) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    info = msgspec.structs.fields(struct_type)
    for field in info:
        if field.default is not msgspec.NODEFAULT:
            defaults[field.name] = field.default
        elif field.default_factory is not msgspec.NODEFAULT:
            defaults[field.name] = None
    return defaults
