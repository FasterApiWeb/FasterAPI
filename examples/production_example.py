"""Example production-oriented stack: correlation IDs, rate limits, pooled DB handle."""

from __future__ import annotations

from FasterAPI import (
    DatabasePoolMiddleware,
    Faster,
    RateLimitMiddleware,
    Request,
    RequestIDMiddleware,
)

# Optional: from FasterAPI.log_config import configure_structlog
# configure_structlog(json_format=True)

app = Faster(title="Production demo", max_body_size=50 * 1024 * 1024)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=300)
app.add_middleware(DatabasePoolMiddleware, pool=None, state_key="db")  # replace None with engine/pool


@app.get("/health")
async def health(request: Request):
    return {"request_id": request.state.get("request_id"), "db": request.state.get("db")}
