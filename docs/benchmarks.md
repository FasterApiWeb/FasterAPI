# Benchmarks

CI publishes numbers from **Python 3.13** on Linux; local runs may differ. Results depend on **hardware**, **Python version**, and **server settings**. Treat absolute
**requests per second** as indicative; compare **ratios** (e.g. FasterAPI vs FastAPI on the
same machine) for regressions.

## What we compare

1. **FasterAPI** — this project (`Faster`), ASGI app under uvicorn where noted.
2. **FastAPI** — same route shapes and payload sizes.
3. **Fiber (Go)** — a tiny Go service in `benchmarks/fiber` with matching routes, for HTTP-level comparison.

Python frameworks are compared in two ways:

- **Direct ASGI:** invokes the ASGI callable in-process (no TCP stack). Stresses routing,
  validation, and serialization.
- **HTTP (httpx):** same client load against **uvicorn** for Python and Fiber’s HTTP server.
  Includes network stack cost on localhost.

## Routing micro-benchmark

The **radix tree** router is compared to a **regex** approach that mirrors many frameworks:
many compiled patterns, match until one succeeds. The workload performs a fixed number of
lookups on representative paths.

## Reproduce locally

```bash
pip install -e ".[dev,benchmark]"
# Direct ASGI + optional full HTTP comparison (starts local servers)
python benchmarks/compare.py --direct
python benchmarks/compare.py --requests 10000 --concurrency 100
```

**Fiber (Go):**

```bash
cd benchmarks/fiber
go build -o fiberbench .
PORT=3099 ./fiberbench
```

Regression floors used in CI live in **`benchmarks/baseline.json`** and are enforced by
**`benchmarks/check_regressions.py`** (ASGI speedup vs FastAPI and radix-vs-regex speedup).

## CI

Pull requests run the benchmark workflow: it **fails** if those floors are breached and posts
a comment with the latest numbers including **Fiber** when the Go binary builds successfully.
