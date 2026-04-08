from __future__ import annotations

import inspect
import re
import types
import typing
from typing import Any, Callable, Union, get_args, get_origin

import msgspec

from ..params import Body, Cookie, Header, Path, Query


def generate_openapi(
    app: Any,
    *,
    title: str = "FasterAPI",
    version: str = "0.1.0",
    description: str = "",
) -> dict[str, Any]:
    """Generate an OpenAPI 3.0.3 spec dict from a Faster app instance."""
    if hasattr(app, "_openapi_cache") and app._openapi_cache is not None:
        result: dict[str, Any] = app._openapi_cache
        return result

    schemas: dict[str, Any] = {}
    paths: dict[str, Any] = {}

    for route in app.routes:
        method = route["method"].lower()
        raw_path = route["path"]
        handler = route["handler"]

        # Convert {param} to OpenAPI {param} (already compatible)
        openapi_path = raw_path

        operation = _build_operation(route, handler, schemas)
        paths.setdefault(openapi_path, {})[method] = operation

    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {
            "title": title,
            "version": version,
        },
        "paths": paths,
    }
    if description:
        spec["info"]["description"] = description
    if schemas:
        spec["components"] = {"schemas": schemas}

    app._openapi_cache = spec
    return spec


def _build_operation(
    route: dict[str, Any],
    handler: Callable,
    schemas: dict[str, Any],
) -> dict[str, Any]:
    operation: dict[str, Any] = {}

    # Tags
    tags = route.get("tags", [])
    if tags:
        operation["tags"] = tags

    # Summary from decorator or function name
    summary = route.get("summary", "")
    if summary:
        operation["summary"] = summary
    else:
        operation["summary"] = handler.__name__.replace("_", " ").title()

    # Description from docstring
    doc = inspect.getdoc(handler)
    if doc:
        operation["description"] = doc

    # Deprecated
    if route.get("deprecated", False):
        operation["deprecated"] = True

    # Operation ID
    operation["operationId"] = handler.__name__

    # Parameters and request body
    parameters, request_body = _extract_params(route, handler, schemas)
    if parameters:
        operation["parameters"] = parameters
    if request_body:
        operation["requestBody"] = request_body

    # Responses
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

    # 422 for routes that have body/query/path params
    if parameters or request_body:
        responses["422"] = {
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
                                        "loc": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "msg": {"type": "string"},
                                        "type": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }

    operation["responses"] = responses
    return operation


def _extract_params(
    route: dict[str, Any],
    handler: Callable,
    schemas: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    parameters: list[dict[str, Any]] = []
    request_body: dict[str, Any] | None = None

    # Extract {param} names from path
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
        annotation = hints.get(name, param.annotation)
        # If annotation is still a string, try to resolve from param default
        if isinstance(annotation, str):
            annotation = param.annotation
        default = param.default

        # Skip Request injection
        from ..request import Request as RequestClass
        if annotation is RequestClass:
            continue

        # Skip Depends
        from ..dependencies import Depends
        if isinstance(default, Depends):
            continue

        # Path parameter
        if isinstance(default, Path) or name in path_param_names:
            p: dict[str, Any] = {
                "name": name,
                "in": "path",
                "required": True,
                "schema": _annotation_to_schema(annotation),
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
                "schema": _annotation_to_schema(annotation),
            }
            if default.description:
                p["description"] = default.description
            if default.default is not None:
                p["schema"]["default"] = default.default
            parameters.append(p)
            continue

        # Header parameter
        if isinstance(default, Header):
            header_name = default.alias or (
                name.replace("_", "-") if default.convert_underscores else name
            )
            p = {
                "name": header_name,
                "in": "header",
                "required": default.default is None,
                "schema": _annotation_to_schema(annotation),
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
                "schema": _annotation_to_schema(annotation),
            }
            if default.default is not None:
                p["schema"]["default"] = default.default
            parameters.append(p)
            continue

        # Body / msgspec.Struct
        if isinstance(default, Body) or _is_struct_type(annotation):
            schema = _type_to_schema(annotation, schemas)
            request_body = {
                "required": True,
                "content": {"application/json": {"schema": schema}},
            }
            continue

    return parameters, request_body


def _is_struct_type(annotation: Any) -> bool:
    return (
        annotation is not inspect.Parameter.empty
        and isinstance(annotation, type)
        and issubclass(annotation, msgspec.Struct)
    )


def _is_optional(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = get_args(annotation)
        return type(None) in args
    return False


def _annotation_to_schema(
    annotation: Any, schemas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}
    return _python_type_to_schema(annotation, schemas)


def _python_type_to_schema(
    tp: Any, schemas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tp is str:
        return {"type": "string"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if tp is bool:
        return {"type": "boolean"}

    # Check if it's a struct type (before checking origin)
    if _is_struct_type(tp):
        if schemas is not None:
            return _struct_to_ref(tp, schemas)
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
        schema = {"type": "object"}
        if args and len(args) == 2:
            schema["additionalProperties"] = _python_type_to_schema(args[1], schemas)
        return schema

    return {"type": "string"}


def _type_to_schema(
    tp: Any, schemas: dict[str, Any],
) -> dict[str, Any]:
    if tp is None or tp is inspect.Parameter.empty:
        return {"type": "string"}

    if _is_struct_type(tp):
        return _struct_to_ref(tp, schemas)

    return _python_type_to_schema(tp, schemas)


def _struct_to_ref(
    struct_type: type, schemas: dict[str, Any],
) -> dict[str, Any]:
    name = struct_type.__name__

    if name not in schemas:
        schemas[name] = _struct_to_schema(struct_type, schemas)

    return {"$ref": f"#/components/schemas/{name}"}


def _struct_to_schema(
    struct_type: type, schemas: dict[str, Any],
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

    # Only use docstring if defined directly on this class, not inherited
    doc = struct_type.__doc__
    if doc and doc != msgspec.Struct.__doc__:
        # Clean up the docstring
        doc = inspect.cleandoc(doc)
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
    # Remove non-field annotations
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
