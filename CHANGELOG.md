# Changelog

All notable changes to FasterAPI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-08

### Added

- **Core framework**: `Faster` application class with full ASGI lifecycle support
  (HTTP, WebSocket, lifespan events)
- **Python 3.13 sub-interpreters**: `SubInterpreterPool` and `run_in_subinterpreter()`
  for true CPU-bound parallelism with per-interpreter GIL (PEP 684/734). Falls back
  to `ProcessPoolExecutor` on Python 3.11–3.12, and older versions.
- **Radix-tree router**: High-performance URL routing (~6x faster than regex),
  with static/parameterized/wildcard paths and trailing-slash normalisation
- **FasterRouter**: Sub-router with prefix and tag support, includable via
  `app.include_router()`
- **Request object**: Parsed headers, query params, path params, cookies,
  client info. Async `json()` and `form()` body parsing
- **Response classes**: `Response`, `JSONResponse`, `HTMLResponse`,
  `PlainTextResponse`, `RedirectResponse`, `StreamingResponse`, `FileResponse`
- **Parameter descriptors**: `Path()`, `Query()`, `Header()`, `Cookie()`,
  `Body()`, `File()`, `Form()` with defaults, aliases, and descriptions
- **Dependency injection**: `Depends()` with recursive resolution, per-request
  caching, sync/async support, and full signature introspection
- **Validation**: msgspec `Struct` body decoding with automatic 422 error
  responses matching FastAPI's error format
- **Exception handling**: `HTTPException`, `RequestValidationError`, custom
  exception handlers via `app.add_exception_handler()`
- **Middleware**: `CORSMiddleware`, `GZipMiddleware`, `TrustedHostMiddleware`,
  `HTTPSRedirectMiddleware`, `BaseHTTPMiddleware` for custom middleware
- **OpenAPI 3.0.3**: Auto-generated spec from route metadata and handler
  signatures, Swagger UI at `/docs`, ReDoc at `/redoc`
- **Background tasks**: `BackgroundTasks` injectable parameter, tasks run after
  response is sent
- **WebSocket**: `WebSocket` class with text/bytes/JSON send/receive, connection
  state tracking, `@app.websocket()` decorator
- **File uploads**: `UploadFile` with `SpooledTemporaryFile` backend (1 MB
  memory threshold), multipart parsing via `python-multipart`
- **Form data**: `FormData` dict with `UploadFile` support, urlencoded and
  multipart parsing
- **Test client**: `TestClient` wrapping `httpx.ASGITransport` for zero-server
  testing, sync HTTP methods, context manager support
- **Status codes**: `status` module with HTTP status constants
  (`status.HTTP_200_OK`, etc.)
- **Concurrency engine**: Python 3.13 sub-interpreters first, then
  ProcessPoolExecutor fallback for 3.11–3.12. Thread pool for I/O-bound work.
  Auto-detect uvloop at startup (optional on 3.13+)
- **Event loop selection**: Tries uvloop first, falls back to stdlib asyncio.
  uvloop is now an optional dependency (not required on 3.13+)
- **Examples**: Basic hello world, full CRUD API, WebSocket chat room
- **Benchmarks**: HTTP head-to-head (FasterAPI vs FastAPI), radix-tree vs regex
  routing profiler with actual measured results
- **CI**: GitHub Actions workflow testing on Python 3.11, 3.12, 3.13
- **Release workflow**: PyPI publishing via trusted publisher on git tags

[0.1.0]: https://github.com/EshwarCVS/FasterAPI/releases/tag/v0.1.0
