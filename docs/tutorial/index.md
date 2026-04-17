# Tutorial — User Guide

This tutorial walks you through FasterAPI **step by step**. Each section builds on the
previous one, so follow them in order if you are new to the framework.

By the end you will know how to:

- declare path, query, header, cookie, and body parameters
- validate and serialize data with **msgspec**
- compose dependencies with `Depends()`
- run background tasks
- handle errors gracefully
- document your API automatically via OpenAPI / Swagger UI

## Prerequisites

- Python 3.10 or later (3.13 recommended)
- Basic familiarity with `async`/`await`
- FasterAPI installed (`pip install faster-api-web`)

## Pages

| Topic | What you learn |
|---|---|
| [Path Parameters](path-parameters.md) | Dynamic path segments, type coercion |
| [Query Parameters](query-parameters.md) | Optional/required query strings, aliases |
| [Request Body](request-body.md) | Typed JSON bodies with `msgspec.Struct` |
| [Response Model](response-model.md) | Return types, status codes, response filtering |
| [Form Data & File Uploads](form-and-files.md) | `Form()`, `File()`, `UploadFile` |
| [Error Handling](error-handling.md) | `HTTPException`, custom exception handlers |
| [Dependencies](dependencies.md) | `Depends()`, scoped DI, chained deps |
| [Background Tasks](background-tasks.md) | Fire-and-forget after the response |
| [Middleware](middleware.md) | CORS, GZip, custom middleware |
| [WebSockets](websockets.md) | Real-time bidirectional connections |
| [Metadata & Docs](metadata.md) | Tags, summaries, OpenAPI customisation |

> **Already a FastAPI user?** See [Migrating from FastAPI](../migration-from-fastapi.md)
> for a focused diff rather than a full walkthrough.
