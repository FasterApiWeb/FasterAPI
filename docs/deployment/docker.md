# Docker

## Project Dockerfile

FasterAPI ships a `Dockerfile` in the repository root.  Here is a production-ready
multi-stage build:

```dockerfile
# ── Build stage ─────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# Install build tools
RUN pip install --upgrade pip

# Copy dependency files first to leverage layer cache
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[all]" --target /app/deps

# ── Runtime stage ────────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /app/deps /usr/local/lib/python3.13/site-packages

# Copy application source
COPY . .

# Non-root user for security
RUN useradd -r -u 1001 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Build and run

```bash
docker build -t my-fasterapi-app .
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@host/db \
  -e SECRET_KEY=your-secret \
  my-fasterapi-app
```

## .dockerignore

```
.git
.venv
__pycache__
*.pyc
*.pyo
.pytest_cache
.mypy_cache
.ruff_cache
*.egg-info
dist/
docs/
tests/
.env
.env.*
```

## docker-compose for local development

```yaml
# docker-compose.yml
version: "3.9"

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@db/mydb
      SECRET_KEY: dev-secret-not-for-production
      DEBUG: "true"
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - .:/app       # live reload in development

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: mydb
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

```bash
docker compose up --build
```

## docker-compose for production

```yaml
# docker-compose.prod.yml
version: "3.9"

services:
  api:
    image: my-fasterapi-app:${VERSION:-latest}
    restart: unless-stopped
    environment:
      DATABASE_URL: ${DATABASE_URL}
      SECRET_KEY: ${SECRET_KEY}
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 512m
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - api
```

## Optimising image size

Use `python:3.13-slim` (not the full image) and avoid installing dev dependencies:

```dockerfile
RUN pip install --no-cache-dir ".[all]"
```

Multi-stage builds keep the final image free of build tools:

```bash
docker images my-fasterapi-app
# REPOSITORY          TAG     SIZE
# my-fasterapi-app    latest  ~120MB
```

## Environment variable secrets

In production, inject secrets via your orchestrator — never bake them into the image:

```bash
# Docker Swarm secrets
docker secret create db_url ./db_url.txt

# Kubernetes — see Kubernetes deployment guide
```

## Python 3.13 with sub-interpreters

Use the official `python:3.13` image for sub-interpreter CPU parallelism.  Set
`GIL=1` only if libraries require it:

```dockerfile
FROM python:3.13
ENV PYTHONGIL=0
```

## Health check

Add a health check so Docker / orchestrators can restart unhealthy containers:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
```

## Next steps

- [Nginx & Traefik](nginx-traefik.md) — TLS and load balancing.
- [Kubernetes](kubernetes.md) — orchestrate at scale.
- [Cloud Services](cloud.md) — managed container services.
