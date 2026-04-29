# v0.4 performance roadmap (notes)

This page expands the **v0.4.0 — Performance** items from the project README: how each fits FasterAPI’s architecture and what operators typically configure outside the framework.

## Cython-compiled hot paths (router, DI resolver)

The radix-tree router (`RadixRouter.resolve` / `_walk`) and the dependency injector (`compile_handler` + `_resolve_from_specs`) are written as plain Python with tight loops and `__slots__`. Compiling those loops with **Cython** (or a small Rust/PyO3 extension) is a plausible win on steady-state throughput benchmarks because request routing and DI run on **every** request.

Practical approach:

- Factor truly hot loops into one module (e.g. `_radix_resolve`) so `.pyx` or ABI-stable `.so` builds stay maintainable.
- Ship wheels selectively (`manylinux`, `macOS`) via CI; fall back to pure Python when no wheel matches (same behaviour).
- Keep `compile_handler` introspection in Python at startup; only per-request resolution moves to compiled code.

## HTTP/3 (QUIC) support

FasterAPI is **ASGI 3**. HTTP versions are negotiated by the **server**, not by framework internals: clients speak HTTP/1.1, HTTP/2, or HTTP/3 (QUIC) to uvicorn/Hypercorn/modern proxies; your app receives ASGI `scope` / `receive` / `send` the same way.

To expose HTTP/3 today:

- Run an ASGI server or proxy that terminates QUIC + TLS (e.g. Hypercorn with HTTP/3 where supported, or put **nginx**, **Envoy**, or **Cloudflare** in front and terminate QUIC there).
- Ensure TLS certificates are configured (QUIC runs over TLS 1.3).

So “HTTP/3 support” for this framework means **documented compatibility + regression-tested ASGI contract**, not embedding an QUIC stack inside FasterAPI.

## Connection-level keep-alive optimisation

Keep-alive is tuned at the **ASGI server** and reverse proxy:

| Layer | Typical knobs |
| ----- | ------------- |
| **Uvicorn** | `--timeout-keep-alive` (seconds idle before closing the connection). |
| **Gunicorn + Uvicorn workers** | `worker_connections`, timeouts on the sync worker front-end. |
| **nginx / Traefik / Envoy** | `keepalive_timeout`, upstream `proxy_http_version`, HTTP/2 or HTTP/3 upstream pools. |

Raising keep-alive reduces TLS handshakes and TCP churn for chatty clients; lowering it frees FDs sooner under connection floods. FasterAPI does not expose these—it delegates to deployment docs (`deployment/`).

## Pre-serialised response caching

Ways to avoid repeated JSON encoding on hot endpoints:

1. **Inline bytes** — `JSONResponse(b'{"status":"ok"}')` sends cached UTF-8 JSON without calling `msgspec` (`advanced/custom-response.md`).
2. **Process-local LRU** — cache encoded bytes keyed by a cheap discriminator (e.g. etag or primary key) in application code.
3. **Redis / CDN** — `RedisCacheMiddleware` caches whole responses for GET (see ecosystem extras).

Combining (1) with immutable payloads removes encoder overhead entirely for fixed dashboards or health payloads.
