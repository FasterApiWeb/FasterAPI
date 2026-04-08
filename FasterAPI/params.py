from __future__ import annotations

from typing import Any

_MISSING = object()


class Path:
    """Declare a path parameter with optional default and description."""

    __slots__ = ("default", "description")

    def __init__(self, default: Any = _MISSING, *, description: str = "") -> None:
        self.default = default
        self.description = description

    def __repr__(self) -> str:
        if self.default is _MISSING:
            return "Path()"
        return f"Path(default={self.default!r})"


class Query:
    """Declare a query parameter with optional default, description, and alias."""

    __slots__ = ("default", "description", "alias")

    def __init__(
        self,
        default: Any = None,
        *,
        description: str = "",
        alias: str | None = None,
    ) -> None:
        self.default = default
        self.description = description
        self.alias = alias

    def __repr__(self) -> str:
        return f"Query(default={self.default!r})"


class Body:
    """Declare a request body parameter with optional default and embed mode."""

    __slots__ = ("default", "description", "embed")

    def __init__(
        self,
        default: Any = _MISSING,
        *,
        description: str = "",
        embed: bool = False,
    ) -> None:
        self.default = default
        self.description = description
        self.embed = embed

    def __repr__(self) -> str:
        if self.default is _MISSING:
            return "Body()"
        return f"Body(default={self.default!r})"


class Header:
    """Declare a header parameter with optional default and alias."""

    __slots__ = ("default", "alias", "convert_underscores")

    def __init__(
        self,
        default: Any = None,
        *,
        alias: str | None = None,
        convert_underscores: bool = True,
    ) -> None:
        self.default = default
        self.alias = alias
        self.convert_underscores = convert_underscores

    def __repr__(self) -> str:
        return f"Header(default={self.default!r})"


class Cookie:
    """Declare a cookie parameter with an optional default value."""

    __slots__ = ("default",)

    def __init__(self, default: Any = None) -> None:
        self.default = default

    def __repr__(self) -> str:
        return f"Cookie(default={self.default!r})"


class File:
    """Declare a file upload parameter."""

    __slots__ = ("description",)

    def __init__(self, *, description: str = "") -> None:
        self.description = description

    def __repr__(self) -> str:
        return "File()"


class Form:
    """Declare a form field parameter with an optional default value."""

    __slots__ = ("default", "description")

    def __init__(self, default: Any = _MISSING, *, description: str = "") -> None:
        self.default = default
        self.description = description

    def __repr__(self) -> str:
        if self.default is _MISSING:
            return "Form()"
        return f"Form(default={self.default!r})"


MISSING = _MISSING
