# systemd Service

Running FasterAPI under **systemd** lets the OS manage your process lifecycle:
auto-start on boot, automatic restart on crash, and centralized log collection
through `journald`.

## Prerequisites

- A Linux host with systemd (Ubuntu 20.04+, Debian 11+, RHEL 8+, etc.)
- FasterAPI installed in a virtualenv at a known path
- A non-root system user to own the process

## Create a system user

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin fasterapi
```

## Install the application

```bash
# Example: install into /opt/myapp
sudo mkdir -p /opt/myapp
sudo python3 -m venv /opt/myapp/.venv
sudo /opt/myapp/.venv/bin/pip install "faster-api-web[all]"
sudo cp -r /path/to/your/app /opt/myapp/app
sudo chown -R fasterapi:fasterapi /opt/myapp
```

## Service unit file

Create `/etc/systemd/system/fasterapi.service`:

```ini
[Unit]
Description=FasterAPI application server
After=network.target
# Uncomment if the app needs PostgreSQL:
# After=network.target postgresql.service
# Requires=postgresql.service

[Service]
Type=exec
User=fasterapi
Group=fasterapi
WorkingDirectory=/opt/myapp/app

# Runtime environment — override in /etc/fasterapi.env
EnvironmentFile=-/etc/fasterapi.env
Environment="PATH=/opt/myapp/.venv/bin:/usr/local/bin:/usr/bin:/bin"

ExecStart=/opt/myapp/.venv/bin/uvicorn main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 4 \
    --log-level info \
    --access-log

# Graceful shutdown: send SIGTERM, wait up to 30 s, then SIGKILL
TimeoutStopSec=30

# Restart policy
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=3

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/myapp

# Resource limits
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

## Environment file

Store secrets outside the unit file so they don't appear in `systemctl status`:

```bash
# /etc/fasterapi.env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/mydb
SECRET_KEY=a-long-random-string-here
ENV=production
LOG_LEVEL=info
```

```bash
sudo chmod 640 /etc/fasterapi.env
sudo chown root:fasterapi /etc/fasterapi.env
```

## Enable and start

```bash
# Reload systemd to pick up the new unit file
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable fasterapi

# Start now
sudo systemctl start fasterapi

# Check status
sudo systemctl status fasterapi
```

Expected output:

```
● fasterapi.service - FasterAPI application server
     Loaded: loaded (/etc/systemd/system/fasterapi.service; enabled)
     Active: active (running) since Mon 2025-01-01 12:00:00 UTC; 3s ago
   Main PID: 12345 (uvicorn)
      Tasks: 5 (limit: 4915)
     Memory: 72.0M
        CPU: 1.234s
```

## Common management commands

| Command | Purpose |
|---|---|
| `sudo systemctl start fasterapi` | Start the service |
| `sudo systemctl stop fasterapi` | Stop gracefully |
| `sudo systemctl restart fasterapi` | Stop then start |
| `sudo systemctl reload fasterapi` | Send SIGHUP (uvicorn: graceful reload) |
| `sudo systemctl status fasterapi` | Current state + last log lines |
| `sudo systemctl enable fasterapi` | Enable on boot |
| `sudo systemctl disable fasterapi` | Disable on boot |
| `sudo journalctl -u fasterapi -f` | Follow live logs |
| `sudo journalctl -u fasterapi --since "1h ago"` | Last hour of logs |

## Zero-downtime reload

Uvicorn supports graceful reload via `--reload` (dev only) or by signaling the
master process.  For production zero-downtime restarts:

```bash
# Send SIGHUP to reload workers without dropping connections
sudo kill -HUP $(systemctl show -p MainPID --value fasterapi)
```

Or use `systemctl reload` if `ExecReload` is configured:

```ini
[Service]
ExecReload=/bin/kill -HUP $MAINPID
```

## Multiple instances (socket activation)

For A/B deployments, use systemd socket activation so the OS holds the socket
while you swap service instances:

```ini
# /etc/systemd/system/fasterapi.socket
[Unit]
Description=FasterAPI socket

[Socket]
ListenStream=0.0.0.0:8000
BindIPv6Only=both

[Install]
WantedBy=sockets.target
```

```ini
# /etc/systemd/system/fasterapi.service (socket-activated variant)
[Unit]
Description=FasterAPI application server
Requires=fasterapi.socket

[Service]
Type=exec
User=fasterapi
ExecStart=/opt/myapp/.venv/bin/uvicorn main:app --fd 0 --workers 4
StandardInput=socket
```

```bash
sudo systemctl enable --now fasterapi.socket
sudo systemctl start fasterapi
```

## Watching logs

```bash
# Real-time structured logs
sudo journalctl -u fasterapi -f -o json-pretty

# Errors only
sudo journalctl -u fasterapi -p err

# Export to file
sudo journalctl -u fasterapi > fasterapi.log
```

## Next steps

- [Gunicorn + Uvicorn](gunicorn.md) — multi-process worker pooling.
- [HTTPS — Let's Encrypt](https.md) — TLS termination with Nginx.
- [Nginx & Traefik](nginx-traefik.md) — reverse proxy setup.
