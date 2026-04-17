# Benchmarks

CI publishes numbers from **Python 3.13** on Linux; local runs may differ. Results
depend on **hardware**, **Python version**, and **server settings**. Treat absolute
**requests per second** as indicative; compare **ratios** (e.g. FasterAPI vs FastAPI
on the same machine) for regressions.

## What we compare

1. **FasterAPI** — this project (`Faster`), ASGI app under uvicorn where noted.
2. **FastAPI** — same route shapes and payload sizes.
3. **Fiber (Go)** — a tiny Go service in `benchmarks/fiber` with matching routes, for HTTP-level comparison.

Python frameworks are compared in two ways:

- **Direct ASGI:** invokes the ASGI callable in-process (no TCP stack). Stresses routing,
  validation, and serialisation.
- **HTTP (httpx):** same client load against **uvicorn** for Python and Fiber's HTTP server.
  Includes network stack cost on localhost.

## Environment specification

Reproducible benchmarks require a consistent environment.  CI runs on:

| Parameter | Value |
|---|---|
| OS | Ubuntu 22.04 (GitHub Actions `ubuntu-latest`) |
| Python | 3.13 (CPython, official installer) |
| CPU | GitHub Actions hosted runner (2 vCPU) |
| Memory | 7 GB |
| uvicorn | latest stable |
| Concurrency | configurable via `--concurrency` flag (default 100) |
| Requests | configurable via `--requests` flag (default 10 000) |

## Routing micro-benchmark

The **radix tree** router is compared to a **regex** approach that mirrors many
frameworks: many compiled patterns, match until one succeeds. The workload performs a
fixed number of lookups on representative paths.

Typical result (run `python benchmarks/compare.py --direct`):

```
Routing benchmark
  Radix tree:  X.XXx  (FasterAPI)
  Regex:        1.00x  (baseline)
  Speedup:      X.XX×
```

The speedup varies with the number of registered routes — radix scales O(k) in key
length while regex scales O(n) in number of patterns.

## ASGI throughput benchmark

In-process ASGI invocation measures the framework overhead without network latency:

```
ASGI throughput (req/s)
  FasterAPI:  XX,XXX req/s
  FastAPI:    XX,XXX req/s
  Speedup:    X.XX×
```

Key contributors to FasterAPI's advantage:

- `msgspec` JSON encode/decode (C extension, ~2-10× faster than Pydantic's encoder)
- Handler compilation at route-registration time (no `inspect.signature` per request)
- Radix tree routing (O(k) vs O(n))
- Optional uvloop event loop

## HTTP benchmark (localhost)

Running real uvicorn servers and measuring with httpx:

```
HTTP throughput (req/s, concurrency=100)
  FasterAPI:  XX,XXX req/s
  FastAPI:    XX,XXX req/s
  Fiber (Go): XX,XXX req/s
```

Go Fiber shows the theoretical ceiling for this hardware — any Python framework sits
below it due to interpreter overhead.

## Regression floors

Regression floors used in CI live in **`benchmarks/baseline.json`** and are enforced
by **`benchmarks/check_regressions.py`**:

```json
{
  "asgi_speedup_vs_fastapi": 1.5,
  "routing_speedup_radix_vs_regex": 2.0
}
```

A PR **fails** if either floor is breached.

## Reproduce locally

```bash
# Install with benchmark extras
pip install -e ".[dev,benchmark]"

# Direct ASGI benchmark (no network overhead)
python benchmarks/compare.py --direct

# HTTP benchmark (starts local servers)
python benchmarks/compare.py --requests 10000 --concurrency 100
```

**Fiber (Go) comparison:**

```bash
cd benchmarks/fiber
go build -o fiberbench .
PORT=3099 ./fiberbench &
python benchmarks/compare.py --requests 10000 --concurrency 100
```

## Interpreting results

- **req/s** — requests per second (higher is better).
- **Ratio** — FasterAPI req/s ÷ FastAPI req/s. A ratio of 2.0 means FasterAPI is
  twice as fast on this workload.
- **Latency percentiles** (p50, p95, p99) are more meaningful than throughput alone
  for production sizing.

## CI

Pull requests run the benchmark workflow: it **fails** if regression floors are
breached and posts a comment with the latest numbers including **Fiber** when the
Go binary builds successfully.

The benchmark results are also automatically synced to the README via the
`sync-benchmark-readme` workflow on pushes to `master`.

## Third-party verification

For independent benchmarks of Python ASGI frameworks, see:

- [TechEmpower Web Framework Benchmarks](https://www.techempower.com/benchmarks/)
- [python-web-benchmarks](https://github.com/mtag-dev/py-web-frameworks-benchmarks)

These measure different workloads and hardware; treat them as directional, not
absolute.
