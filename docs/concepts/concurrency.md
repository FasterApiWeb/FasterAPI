# Concurrency & Parallelism

FasterAPI is designed to extract maximum performance from modern Python.  This page
explains *how* it achieves this and *when* to use each concurrency primitive.

## The Python GIL

Python's Global Interpreter Lock (GIL) ensures only one thread executes Python
bytecode at a time.  This limits true CPU parallelism within a single process.

**async/await sidesteps the GIL** for I/O-bound work because the event loop
cooperatively yields control while waiting — no threads needed.

For **CPU-bound** tasks, the GIL is a real constraint.  FasterAPI offers two
solutions:

1. **`SubInterpreterPool`** (Python 3.13) — true CPU parallelism in a single process.
2. **`ProcessPoolExecutor`** (all Python versions) — multiple processes, each with
   its own GIL.

## FasterAPI's sub-interpreter parallelism

Python 3.13 introduced **sub-interpreters** — isolated Python environments within the
same OS process that each have their own GIL.  FasterAPI's `SubInterpreterPool`
distributes work across them.

```python
from FasterAPI import Faster, run_in_subinterpreter, SubInterpreterPool

app = Faster()


def cpu_heavy(data: bytes) -> bytes:
    # runs in a sub-interpreter — does not block the main event loop
    import hashlib
    return hashlib.sha256(data).hexdigest().encode()


@app.post("/hash")
async def hash_data(request: Request):
    body = await request.body()
    result = await run_in_subinterpreter(cpu_heavy, body)
    return {"hash": result.decode()}
```

### How `SubInterpreterPool` works

1. A pool of worker threads is created at import time, each initialised with its own
   sub-interpreter.
2. `run_in_subinterpreter(func, *args)` serialises the function and arguments,
   dispatches to a free worker, and returns an `asyncio.Future`.
3. The worker runs `func(*args)` in its sub-interpreter (separate GIL → no blocking).
4. The result is deserialised and the future is resolved on the main event loop.

### Fallback on Python < 3.13

On Python 3.10–3.12, `SubInterpreterPool` falls back to `ProcessPoolExecutor`:

```python
# concurrency.py
try:
    # Python 3.13 — true sub-interpreter parallelism
    pool = SubInterpreterPool(max_workers=4)
except RuntimeError:
    # Fallback — process pool
    from concurrent.futures import ProcessPoolExecutor
    pool = ProcessPoolExecutor(max_workers=4)
```

## Event loop: uvloop

On Linux, installing `uvloop` replaces the default asyncio event loop with a
faster implementation (~2× faster I/O dispatch):

```bash
pip install faster-api-web[all]   # includes uvloop
```

FasterAPI installs uvloop automatically at import time when it is available.

## Choosing the right primitive

| Work type | Recommended approach |
|---|---|
| I/O-bound (DB, network, file) | `async def` + `await` |
| CPU-bound (hashing, encoding, ML inference) | `run_in_subinterpreter` |
| CPU-bound, Python < 3.13 | `ProcessPoolExecutor` |
| Blocking sync library | `asyncio.run_in_executor(None, func)` — thread pool |
| Fire-and-forget I/O | `BackgroundTasks` |

## Number of workers

**uvicorn workers** — each handles requests concurrently via async I/O.  A rule of
thumb: `2 × CPU cores + 1`.  With sub-interpreters, a single worker can use all
cores for CPU work.

```bash
uvicorn main:app --workers 4
```

**`SubInterpreterPool` size** — defaults to the number of CPUs.  Tune with:

```python
pool = SubInterpreterPool(max_workers=8)
```

## Concurrency in practice

### Concurrent database queries

```python
import asyncio

@app.get("/dashboard")
async def dashboard():
    users, items, orders = await asyncio.gather(
        fetch_users(),
        fetch_items(),
        fetch_orders(),
    )
    return {"users": users, "items": items, "orders": orders}
```

Three DB queries run concurrently — total time ≈ max(query time), not sum.

### Parallel CPU work

```python
@app.post("/batch-compress")
async def batch_compress(files: list[bytes]):
    results = await asyncio.gather(
        *[run_in_subinterpreter(compress_one, f) for f in files]
    )
    return {"count": len(results)}
```

## Thread safety

- **asyncio primitives** (`asyncio.Lock`, `asyncio.Queue`) — safe for async code.
- **`threading.Lock`** — for sync code in thread-pool callbacks.
- **Sub-interpreters** — isolated; do **not** share Python objects across interpreters.
  Communicate via serialisable data (bytes, ints, strings).

## Next steps

- [Async / Await Primer](async-await.md) — fundamentals.
- [Background Tasks](../tutorial/background-tasks.md) — defer I/O work.
- [Benchmarks](../benchmarks.md) — measured throughput comparisons.
