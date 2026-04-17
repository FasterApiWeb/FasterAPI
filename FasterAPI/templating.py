"""Jinja2 template rendering for FasterAPI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .request import Request
from .response import HTMLResponse, Response

__all__ = ["Jinja2Templates"]


class Jinja2Templates:
    """Render Jinja2 templates as HTML responses.

    Usage::

        templates = Jinja2Templates(directory="templates")

        @app.get("/hello/{name}")
        async def hello(request: Request, name: str):
            return templates.TemplateResponse(request, "hello.html", {"name": name})

    Requires ``jinja2`` to be installed: ``pip install jinja2``.
    """

    def __init__(self, directory: str | Path) -> None:
        try:
            import jinja2
        except ImportError as exc:
            raise ImportError(
                "Jinja2Templates requires jinja2. Install with: pip install jinja2"
            ) from exc

        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(directory)),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )

    def get_template(self, name: str) -> Any:
        return self.env.get_template(name)

    def TemplateResponse(  # noqa: N802
        self,
        request: Request,
        name: str,
        context: dict[str, Any] | None = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str = "text/html",
    ) -> Response:
        ctx = dict(context) if context else {}
        ctx.setdefault("request", request)
        template = self.get_template(name)
        content = template.render(ctx)
        return HTMLResponse(content=content, status_code=status_code, headers=headers)
