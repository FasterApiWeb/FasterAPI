# Nginx & Traefik

A reverse proxy in front of FasterAPI handles TLS termination, load balancing,
rate limiting, and static file serving — letting uvicorn focus on Python.

## Nginx

### Basic configuration

```nginx
# /etc/nginx/conf.d/fasterapi.conf

upstream fasterapi {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;  # optional second worker
    keepalive 16;
}

server {
    listen 80;
    server_name api.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate     /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    add_header X-Content-Type-Options    "nosniff" always;
    add_header X-Frame-Options           "DENY" always;

    location / {
        proxy_pass         http://fasterapi;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade           $http_upgrade;
        proxy_set_header   Connection        "upgrade";
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    # SSE — disable buffering
    location /events {
        proxy_pass         http://fasterapi;
        proxy_set_header   Connection        "";
        proxy_http_version 1.1;
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 3600s;
    }

    # WebSocket
    location /ws {
        proxy_pass         http://fasterapi;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "Upgrade";
    }
}
```

### TLS with Certbot (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d api.example.com
# Auto-renewal
sudo systemctl enable certbot.timer
```

### Rate limiting

```nginx
http {
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

    server {
        location / {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://fasterapi;
        }
    }
}
```

### Gzip (if not using FasterAPI's `GZipMiddleware`)

```nginx
gzip on;
gzip_types application/json text/plain text/css;
gzip_min_length 1000;
```

## Traefik

Traefik is a cloud-native reverse proxy that auto-discovers services via Docker
labels or Kubernetes annotations.

### docker-compose with Traefik

```yaml
# docker-compose.yml
version: "3.9"

services:
  traefik:
    image: traefik:v3
    command:
      - "--api.insecure=false"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.le.acme.httpchallenge=true"
      - "--certificatesresolvers.le.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.le.acme.email=admin@example.com"
      - "--certificatesresolvers.le.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt

  api:
    image: my-fasterapi-app
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=Host(`api.example.com`)"
      - "traefik.http.routers.api.entrypoints=websecure"
      - "traefik.http.routers.api.tls.certresolver=le"
      - "traefik.http.services.api.loadbalancer.server.port=8000"
      # Redirect HTTP → HTTPS
      - "traefik.http.routers.api-http.rule=Host(`api.example.com`)"
      - "traefik.http.routers.api-http.entrypoints=web"
      - "traefik.http.routers.api-http.middlewares=redirect-to-https"
      - "traefik.http.middlewares.redirect-to-https.redirectscheme.scheme=https"
```

### Rate limiting with Traefik middleware

```yaml
labels:
  - "traefik.http.middlewares.ratelimit.ratelimit.average=100"
  - "traefik.http.middlewares.ratelimit.ratelimit.burst=50"
  - "traefik.http.routers.api.middlewares=ratelimit"
```

### Static Traefik config (traefik.yml)

```yaml
entryPoints:
  web:
    address: ":80"
  websecure:
    address: ":443"

certificatesResolvers:
  le:
    acme:
      email: admin@example.com
      storage: /letsencrypt/acme.json
      httpChallenge:
        entryPoint: web

providers:
  docker:
    exposedByDefault: false
```

## FasterAPI root path

Tell FasterAPI the URL prefix used by the proxy (affects Swagger UI server URL):

```bash
uvicorn main:app --root-path /api
```

Or via middleware — see [Behind a Proxy](../advanced/behind-proxy.md).

## Next steps

- [Kubernetes](kubernetes.md) — scale beyond single-host deployments.
- [Cloud Services](cloud.md) — managed proxies on AWS / GCP / Azure.
