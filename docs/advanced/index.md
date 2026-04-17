# Advanced User Guide

This section covers capabilities beyond the basics — production patterns, advanced
OpenAPI customisation, real-time transports, and testing strategies.

## Pages

| Topic | What you learn |
|---|---|
| [Custom Response Classes](custom-response.md) | `Response`, `JSONResponse`, `StreamingResponse`, `FileResponse` |
| [Response Cookies & Headers](response-cookies-headers.md) | Set cookies and custom headers on responses |
| [Using the Request Directly](using-request.md) | Access raw request data, headers, client IP |
| [Settings & Environment Variables](settings.md) | Twelve-factor config with `os.environ` / `python-dotenv` |
| [OpenAPI Customisation](openapi-customization.md) | Conditional docs, extending the schema |
| [Templates (Jinja2)](templates.md) | Server-side HTML rendering |
| [Lifespan Events](lifespan.md) | Startup/shutdown hooks for connections and caches |
| [Behind a Proxy](behind-proxy.md) | Root path, forwarded headers, Nginx/Traefik |
| [Sub-applications](sub-applications.md) | Mount multiple ASGI apps |
| [Server-Sent Events](server-sent-events.md) | Push real-time updates to browsers |
| [Testing with Overrides](testing-overrides.md) | Swap dependencies in tests |
| [Async Tests](async-tests.md) | `pytest-asyncio`, async fixtures |
| [Bigger Applications](bigger-apps.md) | Routers, multiple files, packages |

## Prerequisites

Complete the [Tutorial](../tutorial/index.md) before reading this section.
