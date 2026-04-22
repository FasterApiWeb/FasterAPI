# HTTPS — Let's Encrypt & Nginx

This guide sets up **free, auto-renewing TLS** for a FasterAPI application using
[Let's Encrypt](https://letsencrypt.org/) certificates and Nginx as the TLS-terminating
reverse proxy.

## Architecture

```
Internet → Nginx (port 443, TLS) → FasterAPI / uvicorn (127.0.0.1:8000, plain HTTP)
                ↓ (port 80, HTTP → 301 redirect)
```

Nginx handles encryption; FasterAPI never sees raw TLS.  This is the standard
pattern for production Python web applications.

## Prerequisites

- A VPS or dedicated server with a **public IP address**
- A **domain name** pointed at that IP (A record, propagated)
- Ubuntu / Debian (commands use `apt`; adapt for RHEL/CentOS)
- FasterAPI running locally on `127.0.0.1:8000` (systemd guide: [systemd](systemd.md))

## 1. Install Nginx and Certbot

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

## 2. Initial Nginx configuration (HTTP only)

Certbot needs to verify domain ownership over HTTP before it can issue a certificate.
Create a minimal server block first:

```nginx
# /etc/nginx/sites-available/fasterapi
server {
    listen 80;
    server_name api.example.com;

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Temporary: serve a test response
    location / {
        return 200 "OK";
        add_header Content-Type text/plain;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/fasterapi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 3. Obtain a certificate

```bash
sudo certbot --nginx -d api.example.com --email admin@example.com --agree-tos --no-eff-email
```

Certbot modifies your Nginx config automatically, adding TLS directives and an
HTTP → HTTPS redirect.  For wildcard certificates use the DNS challenge:

```bash
sudo certbot certonly --manual --preferred-challenges dns -d "*.example.com"
```

Certificates are stored in `/etc/letsencrypt/live/api.example.com/`.

## 4. Production Nginx configuration

Replace the site config with a hardened production version:

```nginx
# /etc/nginx/sites-available/fasterapi

# ── HTTP → HTTPS redirect ────────────────────────────────────────────
server {
    listen 80;
    listen [::]:80;
    server_name api.example.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# ── HTTPS ────────────────────────────────────────────────────────────
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name api.example.com;

    # TLS certificates (managed by Certbot)
    ssl_certificate     /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    # Modern TLS settings
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # HSTS — tell browsers to always use HTTPS (1 year)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Security headers
    add_header X-Frame-Options           DENY        always;
    add_header X-Content-Type-Options    nosniff     always;
    add_header Referrer-Policy           "strict-origin-when-cross-origin" always;

    # Proxy settings
    client_max_body_size 10m;

    # ── Proxy to FasterAPI ───────────────────────────────────────────
    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # WebSocket / SSE support
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";

        # Forward client information
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout    60s;
        proxy_read_timeout    60s;

        # Buffer tuning
        proxy_buffering       on;
        proxy_buffer_size     4k;
        proxy_buffers         8 4k;
    }

    # Static files (if any) — serve directly from Nginx
    location /static/ {
        alias /opt/myapp/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## 5. Tell FasterAPI it is behind a proxy

Set `root_path` so OpenAPI URLs and redirects work correctly:

```python
app = Faster(root_path="/")
```

And run uvicorn with the proxy headers trusted:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips="127.0.0.1"
```

See [Behind a Proxy](../advanced/behind-proxy.md) for details.

## 6. Automatic certificate renewal

Certbot installs a systemd timer that runs twice daily:

```bash
sudo systemctl status certbot.timer
# Active: active (waiting)

# Dry-run to verify renewal works
sudo certbot renew --dry-run
```

After renewal, Nginx must reload to pick up the new certificate.  Add a deploy hook:

```bash
# /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
#!/bin/bash
systemctl reload nginx
```

```bash
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

## 7. Verify TLS

```bash
# Check certificate details
openssl s_client -connect api.example.com:443 -servername api.example.com < /dev/null 2>&1 \
  | openssl x509 -noout -dates -issuer

# Grade your TLS configuration (A+ target)
# Visit: https://www.ssllabs.com/ssltest/analyze.html?d=api.example.com

# Check HSTS
curl -sI https://api.example.com | grep -i strict
```

## Nginx performance tuning

```nginx
# /etc/nginx/nginx.conf — global section
worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 4096;
    use epoll;
    multi_accept on;
}

http {
    # Enable keepalive to the upstream
    upstream fasterapi {
        server 127.0.0.1:8000;
        keepalive 32;
    }

    # Gzip compression
    gzip            on;
    gzip_comp_level 5;
    gzip_min_length 256;
    gzip_types      application/json text/plain text/css application/javascript;

    # Connection caching for TLS sessions
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
}
```

## Multiple domains / virtual hosts

Add a second `server` block for each additional domain:

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name internal.example.com;

    ssl_certificate     /etc/letsencrypt/live/internal.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/internal.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8001;  # second FasterAPI instance
        ...
    }
}
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `502 Bad Gateway` | FasterAPI not running | `systemctl status fasterapi` |
| `ERR_SSL_PROTOCOL_ERROR` | Wrong port or Nginx not listening on 443 | `ss -tlnp \| grep nginx` |
| Certificate expired | Renewal hook not firing | `certbot renew --force-renewal` |
| `X-Forwarded-For` shows nginx IP | `proxy_set_header` missing | Check Nginx config |
| OpenAPI docs links broken | `root_path` not set | `Faster(root_path="/")` |

## Next steps

- [Behind a Proxy](../advanced/behind-proxy.md) — configure FasterAPI for proxy headers.
- [Nginx & Traefik](nginx-traefik.md) — advanced reverse proxy patterns.
- [Gunicorn + Uvicorn](gunicorn.md) — multi-worker production setup.
