# Templates (Jinja2)

FasterAPI is ASGI-native and has no built-in template engine, but integrating
**Jinja2** for server-side HTML rendering is straightforward.

## Installation

```bash
pip install jinja2
```

## Basic setup

```python
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from FasterAPI import Faster, Request
from FasterAPI.response import HTMLResponse

app = Faster()

templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=True,
)


def render(name: str, **context) -> HTMLResponse:
    tmpl = templates.get_template(name)
    return HTMLResponse(tmpl.render(**context))
```

## Template directory layout

```
myapp/
├── main.py
└── templates/
    ├── base.html
    ├── index.html
    └── items/
        ├── list.html
        └── detail.html
```

## Example templates

`templates/base.html`:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{% block title %}FasterAPI App{% endblock %}</title>
</head>
<body>
  <nav><a href="/">Home</a> | <a href="/items">Items</a></nav>
  {% block content %}{% endblock %}
</body>
</html>
```

`templates/items/list.html`:

```html
{% extends "base.html" %}
{% block title %}Items{% endblock %}
{% block content %}
<h1>Items</h1>
<ul>
  {% for item in items %}
  <li><a href="/items/{{ item.id }}">{{ item.name }}</a></li>
  {% endfor %}
</ul>
{% endblock %}
```

## Route handlers

```python
@app.get("/")
async def homepage(request: Request):
    return render("index.html", request=request)


@app.get("/items")
async def item_list(request: Request):
    items = [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]
    return render("items/list.html", request=request, items=items)


@app.get("/items/{item_id}")
async def item_detail(item_id: int, request: Request):
    item = {"id": item_id, "name": f"Item {item_id}"}
    return render("items/detail.html", request=request, item=item)
```

## Serving static files

Mount a static-file handler using any ASGI-compatible static server.  A simple
option using `whitenoise`:

```bash
pip install whitenoise
```

```python
from whitenoise import WhiteNoise
import os

# Wrap app with WhiteNoise AFTER creating Faster instance
# WhiteNoise requires wrapping at the ASGI level
static_app = WhiteNoise(app, root="static/", prefix="static")
```

Run with: `uvicorn main:static_app`

Or serve files directly from a route:

```python
from FasterAPI import FileResponse


@app.get("/static/{filename}")
async def static_file(filename: str):
    path = Path("static") / filename
    if not path.exists():
        from FasterAPI import HTTPException
        raise HTTPException(404)
    return FileResponse(path)
```

## Caching templates in production

```python
from jinja2 import Environment, FileSystemLoader, BytecodeCache
import os

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=True,
    # Enable bytecode cache in production for faster rendering
    bytecode_cache=BytecodeCache() if os.environ.get("ENV") == "production" else None,
)
```

## Context processors

Share common data (e.g. current user) across all templates:

```python
def base_context(request: Request) -> dict:
    return {
        "request": request,
        "app_name": "My FasterAPI App",
    }


def render(name: str, request: Request, **extra) -> HTMLResponse:
    ctx = {**base_context(request), **extra}
    return HTMLResponse(templates.get_template(name).render(**ctx))
```

## Next steps

- [Custom Response Classes](custom-response.md) — return HTML, streams, files.
- [Lifespan Events](lifespan.md) — initialise the template engine once at startup.
