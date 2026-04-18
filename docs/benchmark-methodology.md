# Benchmark Methodology

This page explains how FasterAPI's performance claims are measured, what hardware was used, and how to reproduce the results yourself.

---

## Benchmark Types

We run three categories of benchmarks:

| Category | What it measures | How |
|---|---|---|
| **Component** | Individual operations (routing, JSON encode/decode) | Tight loop, `time.perf_counter()` |
| **Framework (Direct ASGI)** | Full request cycle without network overhead | Synthetic ASGI scope → `app(scope, receive, send)` |
| **End-to-End HTTP** | Real HTTP performance including server + network | `httpx.AsyncClient` against a live uvicorn server |

The README numbers come from **Framework (Direct ASGI)** benchmarks — these isolate the framework's actual performance without conflating uvicorn's overhead.

---

## Hardware & Environment

### README Baseline (Python 3.13.7)

```
Machine:    Apple Silicon (M-series)
OS:         macOS
Python:     3.13.7
uvloop:     0.21.x
msgspec:    0.19.x
FastAPI:    0.115.x (comparison target)
Pydantic:   2.10.x
```

### CI Benchmark Runner

```
Machine:    GitHub Actions ubuntu-latest (2-core x86_64)
OS:         Ubuntu 22.04
Python:     3.13
```

!!! note
    CI runners are significantly slower than local Apple Silicon. The CI benchmark workflow compares **speedup ratios** (FasterAPI/FastAPI), not raw req/s, to account for hardware differences.

---

## Direct ASGI Benchmark (Primary)

This is the main benchmark used for the README results. It bypasses the network layer entirely.

### What it does

1. Creates both a FasterAPI and FastAPI app with identical routes
2. Constructs synthetic ASGI `scope`, `receive`, `send` functions
3. Calls `await app(scope, receive, send)` in a tight loop
4. Measures throughput in requests/second

### Routes tested

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Minimal handler — measures framework dispatch overhead |
| `/users/{id}` | GET | Path parameter extraction + JSON response |
| `/users` | POST | JSON body parsing + validation + response |

### Protocol

```
1. Warm-up phase:  500 requests (not timed)
2. Measured phase:  50,000 requests
3. Timing:         time.perf_counter() around the measured phase
4. Result:         requests / elapsed_seconds
```

Both frameworks are benchmarked in the same process, same event loop, same Python version. This eliminates environmental variance.

### Code

The benchmark is in `benchmarks/compare.py`. Run with `--direct` flag:

```bash
python benchmarks/compare.py --direct
```

---

## Component Benchmarks

### Routing (Radix Tree vs Regex)

```
Setup:
  - 100 routes registered (50 static, 30 single-param, 20 multi-param)
  - 3 representative lookup paths tested
  - 500,000 iterations × 3 paths = 1,500,000 total lookups

Measured: ops/second for each router implementation
```

### JSON Encoding (msgspec vs json.dumps)

```
Setup:
  - Dict payload: {"id": 42, "name": "test", "email": "t@t.com", "scores": [1,2,3]}
  - 1,000,000 iterations

Measured: encode ops/second
```

### JSON Decode + Validate (msgspec vs Pydantic v2)

```
Setup:
  - Same payload as encoding, as raw bytes
  - Decoded into a typed Struct/BaseModel
  - 1,000,000 iterations

Measured: decode+validate ops/second
```

---

## How to Reproduce

### Prerequisites

```bash
cd FasterAPI
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,benchmark]"
```

### Run all benchmarks

```bash
python benchmarks/compare.py
```

### Run only the direct ASGI benchmark (fastest, most accurate)

```bash
python benchmarks/compare.py --direct
```

### Run individual component benchmarks

```python
import time
import msgspec
import json

data = {"id": 42, "name": "test", "scores": [1, 2, 3]}
N = 1_000_000

# msgspec
start = time.perf_counter()
for _ in range(N):
    msgspec.json.encode(data)
msgspec_rps = N / (time.perf_counter() - start)

# stdlib json
start = time.perf_counter()
for _ in range(N):
    json.dumps(data).encode()
json_rps = N / (time.perf_counter() - start)

print(f"msgspec: {msgspec_rps:,.0f} ops/s")
print(f"json:    {json_rps:,.0f} ops/s")
print(f"speedup: {msgspec_rps/json_rps:.1f}x")
```

---

## CI Benchmark Workflow

Every PR to `stage` or `master` triggers an automated benchmark that:

1. Runs the direct ASGI benchmark (50,000 requests per endpoint)
2. Runs the routing benchmark (1.5M lookups)
3. Posts a comment on the PR with results

### How to read the PR comment

```
| Endpoint         | FasterAPI      | FastAPI       | Speedup | vs Baseline |
|------------------|----------------|---------------|---------|-------------|
| GET /health      | 150,000/s      | 22,000/s      | 6.82x   | ⚪ -0.4%    |
| GET /users/{id}  | 128,000/s      | 15,000/s      | 8.53x   | ⚪ -2.3%    |
| POST /users      | 95,000/s       | 13,000/s      | 7.31x   | 🟢 +2.2%   |
```

- **Speedup** = FasterAPI req/s ÷ FastAPI req/s
- **vs Baseline** compares the speedup ratio against the README baseline
- 🟢 = speedup improved by >2%
- ⚪ = within noise (±5%)
- 🔴 = speedup regressed by >5% — needs investigation

!!! note
    Raw req/s on CI runners will be 2-3x lower than local Apple Silicon. This is expected. The **speedup ratio** is hardware-independent and is what matters.

---

## Fairness & Methodology Notes

1. **Same process, same loop** — Both frameworks run in the same Python process and event loop. No one gets a "warm" advantage.

2. **Warm-up phase** — 500 requests are run before timing starts to ensure JIT-like optimizations (e.g., `__pycache__`, `lru_cache` warming) are accounted for.

3. **Identical routes** — Both apps define the exact same endpoints with equivalent handler logic. The FasterAPI handler uses `msgspec.Struct`, FastAPI uses `pydantic.BaseModel`.

4. **No GC interference** — The benchmark runs long enough (50K requests) that GC pauses are amortized and don't skew results.

5. **Deterministic input** — The same request payload is used for every iteration. No randomness that could cause branch prediction differences.

6. **Open source** — All benchmark code is in `benchmarks/compare.py`. Run it yourself.
