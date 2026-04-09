# FasterAPI

**PyPI package:** [`faster-api-web`](https://pypi.org/project/faster-api-web/) — `pip install faster-api-web`  
**Documentation** assumes **Python 3.10+**, with examples tuned for **Python 3.13** (see [Python 3.13 & compatibility](python-313.md) for fallbacks on older versions).

FasterAPI is an **ASGI web framework** that keeps a **FastAPI-like API** while swapping heavy
internals for faster building blocks: **msgspec** for models and JSON, a **radix router** for paths,
and **uvloop** where it helps.

Use this site for **installation**, a **CRUD tutorial**, **migration notes** from FastAPI,
**benchmark methodology**, and the **API reference**. Inspiration and credit for the FastAPI
ecosystem are on the [Acknowledgments](acknowledgments.md) page.

!!! tip "Install from PyPI"

    ```bash
    pip install faster-api-web
    ```

    Package name on PyPI is **`faster-api-web`**; you import **`FasterAPI`** in Python.

## When to choose it

- You want **routing and request handling** that stays fast as you add more routes.
- You are fine defining request/response bodies with **msgspec.Struct** instead of Pydantic `BaseModel`.
- You want to stay close to **FastAPI patterns** (`get`/`post`, `Depends`, `HTTPException`, OpenAPI docs).

## Learn next

- [Getting started](getting-started.md) — minimal app and dev server
- [Tutorial: CRUD app](tutorial-crud.md) — in-memory REST API
- [Migrating from FastAPI](migration-from-fastapi.md) — practical renames and model changes
- [Benchmarks](benchmarks.md) — what we measure and how to reproduce results
- [API reference](api-reference.md) — `Faster`, parameters, responses, middleware
