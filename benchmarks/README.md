# FasterAPI Benchmarks

## Prerequisites

```bash
pip install fastapi uvicorn httpx
```

## 1. HTTP Benchmark — FasterAPI vs FastAPI

Starts both frameworks on separate ports, fires concurrent requests, and
prints a comparison table with req/s, p50/p95/p99 latency, and error rate.

```bash
# Default: 10,000 requests, 100 concurrent
python benchmarks/compare.py

# Custom parameters
python benchmarks/compare.py --requests 5000 --concurrency 50
```

Three endpoints are benchmarked head-to-head:

| Endpoint | What it tests |
|---|---|
| `GET /health` | Minimal JSON response (framework overhead) |
| `GET /users/{id}` | Path parameter extraction |
| `POST /users` | JSON body parsing and validation |

Both apps use the same handler logic. FasterAPI uses `msgspec.Struct`,
FastAPI uses `pydantic.BaseModel`.

## 2. Routing Profile — Radix Tree vs Regex

Profiles route resolution with 100 routes and up to 1M lookups using
`cProfile`. Compares the radix-tree router against a naive regex-based
router.

```bash
# Default: 1,000,000 lookups
python benchmarks/profile_routing.py

# Custom lookup count
python benchmarks/profile_routing.py --lookups 500000
```

Output includes:
- Timing comparison table (ops/s, speedup)
- `cProfile` top-20 hotspots for each router

## Interpreting Results

- **Req/s**: Higher is better. Measures end-to-end throughput including
  serialization, routing, and ASGI overhead.
- **p50/p95/p99 latency**: Lower is better. Shows tail latency behavior
  under concurrency.
- **Ops/s (routing)**: Higher is better. Isolates router lookup speed
  without network or serialization overhead.
- Results vary by machine. Run multiple times for stable numbers.
