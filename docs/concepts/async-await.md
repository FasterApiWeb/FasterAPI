# Async / Await Primer

FasterAPI is built on **asyncio** — Python's standard library for writing concurrent
code using coroutines.  This page explains the fundamentals you need to use FasterAPI
effectively.

## The problem async solves

A traditional web server handles one request at a time per thread.  While waiting for
a database query or an external API call, the thread sits idle, wasting resources.

**Async I/O** lets a single thread handle *thousands* of requests simultaneously by
**yielding control** during waits instead of blocking.

## Coroutines and `async def`

An `async def` function is a **coroutine function**.  Calling it returns a coroutine
object; it does not execute immediately.

```python
async def fetch_data():
    return 42

coro = fetch_data()   # coroutine object — not yet run
result = await coro   # now it runs and returns 42
```

`await` can only be used inside an `async def` function.

## The event loop

The event loop is the scheduler that runs coroutines.  ASGI servers (uvicorn,
hypercorn) manage the event loop for you.

```python
import asyncio

async def main():
    print("Hello")
    await asyncio.sleep(1)
    print("World")

asyncio.run(main())   # starts the event loop
```

## `await` suspends, not blocks

When your code hits `await some_io()`, it pauses *that coroutine* and lets the event
loop run other tasks.  When the I/O completes, the coroutine resumes.

```python
import asyncio
import time

async def task(name, delay):
    print(f"{name} started")
    await asyncio.sleep(delay)   # yields control
    print(f"{name} done")

async def main():
    start = time.perf_counter()
    await asyncio.gather(
        task("A", 1),
        task("B", 1),
    )
    elapsed = time.perf_counter() - start
    print(f"Total: {elapsed:.1f}s")   # ~1s, not 2s

asyncio.run(main())
```

Both tasks run concurrently — total time is ~1 second.

## Route handlers in FasterAPI

All FasterAPI route handlers should be `async def`:

```python
@app.get("/items")
async def list_items():
    data = await db.fetch("SELECT * FROM items")   # non-blocking
    return data
```

Sync handlers are also supported but they block the event loop:

```python
# Acceptable for very fast operations; problematic for I/O
@app.get("/sync")
def sync_handler():
    return {"ok": True}
```

## CPU-bound work

`asyncio` does **not** parallelise CPU-bound work — it only helps with I/O.  For
CPU-heavy tasks use:

- `asyncio.get_running_loop().run_in_executor(None, cpu_func)` — thread pool
- `asyncio.get_running_loop().run_in_executor(ProcessPoolExecutor(), cpu_func)` — process pool
- `SubInterpreterPool` (Python 3.13) — see [Concurrency & Parallelism](concurrency.md)

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

executor = ProcessPoolExecutor()


def heavy_computation(n: int) -> int:
    return sum(range(n))


@app.get("/compute")
async def compute(n: int = 1_000_000):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, heavy_computation, n)
    return {"result": result}
```

## Common mistakes

### Forgetting `await`

```python
# BAD — returns coroutine object, not the data
data = db.fetch("SELECT ...")

# GOOD
data = await db.fetch("SELECT ...")
```

### Calling sync I/O from async context

Sync calls (e.g. `requests.get(...)`, `time.sleep(...)`) **block the event loop**,
starving all other concurrent requests.

```python
# BAD
@app.get("/data")
async def get_data():
    import requests
    r = requests.get("https://api.example.com/data")  # blocks event loop!
    return r.json()

# GOOD
@app.get("/data")
async def get_data():
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get("https://api.example.com/data")
    return r.json()
```

### Mixing `asyncio.run` inside a running event loop

```python
# BAD inside a route handler
asyncio.run(some_coroutine())   # raises RuntimeError

# GOOD — await directly
await some_coroutine()
```

## Useful `asyncio` primitives

| Primitive | Purpose |
|---|---|
| `asyncio.gather(*coros)` | Run coroutines concurrently, return all results |
| `asyncio.wait_for(coro, timeout)` | Cancel if not done within timeout |
| `asyncio.sleep(seconds)` | Non-blocking pause |
| `asyncio.create_task(coro)` | Schedule coroutine in background |
| `asyncio.Queue` | Producer-consumer pattern |
| `asyncio.Lock` | Mutual exclusion for shared state |

## Next steps

- [Concurrency & Parallelism](concurrency.md) — how FasterAPI uses sub-interpreters.
- [Background Tasks](../tutorial/background-tasks.md) — fire-and-forget after response.
