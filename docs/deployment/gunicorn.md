# Gunicorn + Uvicorn Workers

**Gunicorn** is a battle-tested WSGI/ASGI process manager.  **Uvicorn** provides the
ASGI worker class.  Together they give you:

- Pre-fork worker pool managed by a supervisor process
- Automatic worker restart on crash
- Graceful rolling restarts with zero downtime
- OS signal-based configuration reload

!!! note "When to use this pattern"
    A single `uvicorn` process already handles thousands of concurrent connections
    via async I/O.  Add Gunicorn when you need **multi-core CPU utilisation** without
    Kubernetes/Docker orchestration, or when your infrastructure team requires Gunicorn
    for consistency with other Python services.

## Install

```bash
pip install gunicorn uvicorn[standard]
```

## Quickstart

```bash
gunicorn main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 4 \
    --bind 0.0.0.0:8000
```

## Worker count guidelines

```
workers = (2 × CPU cores) + 1
```

| vCPUs | Recommended workers |
|---|---|
| 1 | 3 |
| 2 | 5 |
| 4 | 9 |
| 8 | 17 |

Each Uvicorn worker is an async event loop, so it handles many concurrent
connections.  More workers = more parallelism for CPU-bound code but also more
memory.

Check your core count:

```bash
nproc   # Linux
```

## gunicorn.conf.py

Keep all configuration in a file rather than long command-line flags:

```python
# gunicorn.conf.py
import multiprocessing

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
worker_class = "uvicorn.workers.UvicornWorker"
workers = multiprocessing.cpu_count() * 2 + 1
worker_connections = 1000
max_requests = 10_000          # restart worker after N requests (prevents memory leaks)
max_requests_jitter = 1_000    # randomise to prevent thundering-herd restarts

# Timeouts
timeout = 30           # worker killed if no response within 30 s
graceful_timeout = 30  # time allowed for in-flight requests on SIGTERM
keepalive = 5          # seconds to keep idle connections open

# Logging
accesslog = "-"        # stdout
errorlog = "-"         # stderr
loglevel = "info"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sμs'

# Process naming
proc_name = "fasterapi"

# Security: drop privileges after binding
user = "fasterapi"
group = "fasterapi"

# Preload app for faster worker fork and shared memory
preload_app = True
```

Run with the config file:

```bash
gunicorn main:app -c gunicorn.conf.py
```

## UvicornH11Worker vs UvicornWorker

| Worker class | HTTP/2 | WebSocket | When to use |
|---|---|---|---|
| `uvicorn.workers.UvicornWorker` | No (HTTP/1.1 only) | Yes | Behind a reverse proxy that terminates HTTP/2 (recommended) |
| `uvicorn.workers.UvicornH11Worker` | No | Yes | Explicit h11 parser; slightly more strict |

Always terminate HTTP/2 at Nginx/Traefik and use plain HTTP/1.1 between the
proxy and Gunicorn.

## systemd integration

Combine with the [systemd guide](systemd.md):

```ini
[Unit]
Description=FasterAPI via Gunicorn
After=network.target

[Service]
Type=notify
User=fasterapi
Group=fasterapi
WorkingDirectory=/opt/myapp/app
EnvironmentFile=-/etc/fasterapi.env
Environment="PATH=/opt/myapp/.venv/bin:/usr/bin:/bin"

ExecStart=/opt/myapp/.venv/bin/gunicorn main:app \
    --config /opt/myapp/gunicorn.conf.py

ExecReload=/bin/kill -s HUP $MAINPID

TimeoutStopSec=30
KillMode=mixed
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`KillMode=mixed` sends SIGTERM to the master (triggers graceful drain) and
SIGKILL to any remaining workers after `TimeoutStopSec`.

## Zero-downtime rolling restart

```bash
# Signal master to spawn new workers then kill old ones gracefully
kill -USR2 $(cat /var/run/gunicorn.pid)
# Old master exits after new master is healthy
kill -WINCH $(cat /var/run/gunicorn.pid.2)
```

Or via systemd:

```bash
sudo systemctl reload fasterapi   # sends SIGHUP → graceful reload
```

## Monitoring worker health

```bash
# List all gunicorn processes
ps aux | grep gunicorn

# Check master PID
cat /var/run/gunicorn.pid

# Worker restarts (high count → memory leak or crash loop)
journalctl -u fasterapi | grep "Worker exiting"
```

## Pre-loading and shared state

`preload_app = True` imports your app **once** in the master before forking.
Workers share the code segment (copy-on-write), reducing total memory use.

!!! warning
    Do **not** open database connections or asyncio event loops at import time
    when `preload_app = True`.  Each forked worker needs its own connection pool.
    Use a [lifespan handler](../advanced/lifespan.md) instead.

```python
# main.py — safe with preload_app
from contextlib import asynccontextmanager
from FasterAPI import Faster
import databases

DATABASE_URL = "postgresql+asyncpg://..."

@asynccontextmanager
async def lifespan(app):
    # Opens AFTER fork — each worker gets its own pool
    app.state.db = databases.Database(DATABASE_URL)
    await app.state.db.connect()
    yield
    await app.state.db.disconnect()

app = Faster(lifespan=lifespan)
```

## Performance tuning

| Option | Value | Effect |
|---|---|---|
| `worker_connections` | 1000–4000 | Max simultaneous connections per worker |
| `max_requests` | 5000–20000 | Restart worker after N requests (memory hygiene) |
| `keepalive` | 2–75 | Reuse TCP connections; match your load balancer timeout |
| `timeout` | 30–120 | Kill unresponsive workers; set > your slowest endpoint |
| `preload_app` | `True` | Share code pages across workers |

## Docker + Gunicorn

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml gunicorn.conf.py ./
RUN pip install --no-cache-dir ".[all]" gunicorn

COPY app/ app/

RUN useradd -r -u 1001 fasterapi
USER fasterapi

EXPOSE 8000
CMD ["gunicorn", "app.main:app", "--config", "gunicorn.conf.py"]
```

## Next steps

- [systemd Service](systemd.md) — process supervision on Linux.
- [HTTPS — Let's Encrypt](https.md) — TLS in front of Gunicorn.
- [Docker](docker.md) — containerising the app.
