# Deployment

This section covers deploying a FasterAPI application to production — from containers
to cloud platforms to bare-metal servers.

## Pages

| Topic | What you learn |
|---|---|
| [Docker](docker.md) | Dockerfile, multi-stage builds, docker-compose |
| [systemd Service](systemd.md) | Service unit file, auto-start, journald logging |
| [Gunicorn + Uvicorn](gunicorn.md) | Multi-process worker pooling, production config |
| [HTTPS — Let's Encrypt](https.md) | Free TLS certificates with Certbot and Nginx |
| [Nginx & Traefik](nginx-traefik.md) | Reverse proxy, TLS termination, load balancing |
| [Cloud Services](cloud.md) | AWS, GCP, Azure deployment options |
| [Kubernetes](kubernetes.md) | Manifests, health checks, rolling updates |

## ASGI servers

FasterAPI is an ASGI application; you need an ASGI server to run it:

| Server | Notes |
|---|---|
| **uvicorn** | Recommended. Lightweight, production-ready. |
| **hypercorn** | Supports HTTP/2 and HTTP/3. |
| **daphne** | Django Channels' server; ASGI-native. |
| **granian** | Rust-based; very fast. |

### uvicorn (recommended)

```bash
pip install uvicorn[standard]

# Development
uvicorn main:app --reload

# Production (multiple workers)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Hypercorn

```bash
pip install hypercorn

hypercorn main:app --bind 0.0.0.0:8000 --workers 4
```

Hypercorn supports HTTP/2 with TLS:

```bash
hypercorn main:app --bind 0.0.0.0:443 \
  --keyfile key.pem --certfile cert.pem
```

### Daphne

```bash
pip install daphne

daphne -b 0.0.0.0 -p 8000 main:app
```

## Number of workers

A rule of thumb for CPU-bound workloads: **2 × CPU cores + 1**.
For I/O-bound APIs, experiment with higher values.

```bash
uvicorn main:app --workers $(( 2 * $(nproc) + 1 ))
```

For Python 3.13 with `SubInterpreterPool`, a single uvicorn worker can leverage
multiple CPU cores — see [Concurrency & Parallelism](../concepts/concurrency.md).

## Environment variables

Always configure the application through environment variables in production.
See [Settings & Environment Variables](../advanced/settings.md).

## Health checks

Expose a `/health` endpoint for load balancers and container orchestrators:

```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

## Next steps

- [Docker](docker.md) — containerise your app.
- [systemd Service](systemd.md) — run as a managed Linux service.
- [Gunicorn + Uvicorn](gunicorn.md) — multi-worker process pooling.
- [HTTPS — Let's Encrypt](https.md) — free TLS with Certbot and Nginx.
- [Nginx & Traefik](nginx-traefik.md) — reverse proxy and load balancing.
