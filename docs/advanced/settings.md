# Settings & Environment Variables

Twelve-factor applications read configuration from the environment. This page shows
patterns for managing settings in a FasterAPI project.

## Reading from `os.environ`

The simplest approach — read environment variables directly:

```python
import os
from FasterAPI import Faster

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")
SECRET_KEY = os.environ["SECRET_KEY"]  # raises KeyError if missing
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

app = Faster(title="My App")
```

## Using `python-dotenv` for local development

Install:

```bash
pip install python-dotenv
```

Create a `.env` file (never commit it):

```env
DATABASE_URL=postgresql://user:pass@localhost/mydb
SECRET_KEY=dev-secret-do-not-use-in-prod
DEBUG=true
```

Load it before reading variables:

```python
from dotenv import load_dotenv
load_dotenv()   # must run before os.environ reads

import os
DATABASE_URL = os.environ["DATABASE_URL"]
```

## Settings class pattern

Group all settings in a dataclass for easy access and type safety:

```python
import os
import msgspec


class Settings(msgspec.Struct):
    database_url: str
    secret_key: str
    debug: bool = False
    allowed_hosts: list[str] = []
    workers: int = 1


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        secret_key=os.environ["SECRET_KEY"],
        debug=os.environ.get("DEBUG", "false").lower() == "true",
        allowed_hosts=os.environ.get("ALLOWED_HOSTS", "").split(","),
        workers=int(os.environ.get("WORKERS", "1")),
    )


settings = load_settings()
```

## Injecting settings via `Depends`

```python
from FasterAPI import Depends
from functools import lru_cache


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@app.get("/config-info")
async def config_info(cfg: Settings = Depends(get_settings)):
    return {"debug": cfg.debug, "workers": cfg.workers}
```

Using `lru_cache` means settings are loaded once and reused on every request.

## Environment-specific files

```
.env              # shared defaults (safe to commit if no secrets)
.env.local        # local overrides (git-ignored)
.env.production   # production values (never in repo)
```

```python
from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv(".env.local", override=True)
```

## Validating configuration at startup

Fail fast if required variables are missing:

```python
import sys

REQUIRED = ["DATABASE_URL", "SECRET_KEY"]

missing = [k for k in REQUIRED if not os.environ.get(k)]
if missing:
    print(f"Missing required environment variables: {missing}", file=sys.stderr)
    sys.exit(1)
```

Or raise in a lifespan handler — see [Lifespan Events](lifespan.md).

## Using settings in `Faster()` constructor

```python
app = Faster(
    title="My API",
    version=settings.app_version,
    # Hide docs in production
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)
```

## Docker / container environments

Pass settings as environment variables in `docker-compose.yml`:

```yaml
services:
  api:
    image: my-app
    environment:
      DATABASE_URL: postgresql://postgres:pass@db/mydb
      SECRET_KEY: ${SECRET_KEY}   # from host environment
```

## Next steps

- [Lifespan Events](lifespan.md) — initialise connections using settings at startup.
- [Deployment: Docker](../deployment/docker.md) — full container deployment guide.
