# Sub-Interpreters Guide

This page is a deep dive into Python's sub-interpreter support (PEP 684 / PEP 734) and how FasterAPI uses it for CPU-bound parallelism.

---

## The GIL Problem

Python's Global Interpreter Lock (GIL) prevents true parallel execution of Python bytecode across threads in the same process. For I/O-bound work this doesn't matter (threads release the GIL during I/O), but for CPU-bound work it's a hard ceiling:

```
Thread 1:  [compute]---[wait for GIL]---[compute]---[wait for GIL]
Thread 2:  [wait for GIL]---[compute]---[wait for GIL]---[compute]
                    ↑
            Only one thread runs Python at a time
```

Before Python 3.13, the only way to achieve CPU parallelism in Python was `multiprocessing` / `ProcessPoolExecutor`:

```
Process 1 (own GIL):  [compute]────────────────────────
Process 2 (own GIL):  [compute]────────────────────────
                       ↑
               True parallel, but expensive:
               - Fork/spawn overhead (~100ms)
               - Memory duplication
               - Arguments must be picklable
               - No shared state
```

---

## PEP 684 & PEP 734: Per-Interpreter GIL

### PEP 684 (Python 3.12) — The Foundation

Added per-interpreter GIL support at the C level. Each sub-interpreter can optionally have its own GIL, meaning Python bytecode in different interpreters runs truly in parallel.

**Python 3.12 status:** Available via the C API only. No Python-level access.

### PEP 734 (Python 3.13) — The Python API

Exposed sub-interpreters via the `interpreters` stdlib module, making them accessible from pure Python.

```python
import interpreters

interp = interpreters.create()
interp.call(some_function, arg1, arg2)
interp.close()
```

**Python 3.13 status:** Experimental. The `interpreters` module may not be available in all builds. FasterAPI detects this at import time and falls back gracefully.

---

## How Sub-Interpreters Compare

```
                        ┌──────────────┬─────────────┬──────────────────┐
                        │   Threads    │  Processes  │ Sub-Interpreters │
├───────────────────────┼──────────────┼─────────────┼──────────────────┤
│ True CPU parallelism  │      No      │     Yes     │       Yes        │
│ Startup cost          │    ~0.1ms    │   ~100ms    │      ~1ms        │
│ Memory overhead       │     Low      │    High     │     Medium       │
│ Shared state          │     Yes      │      No     │       No         │
│ Argument passing      │   Direct     │   Pickle    │   Shareable*     │
│ GIL                   │   Shared     │  Per-proc   │  Per-interp      │
│ Best for              │  I/O-bound   │  CPU-bound  │   CPU-bound      │
└───────────────────────┴──────────────┴─────────────┴──────────────────┘

* "Shareable" means types that implement the buffer protocol (bytes,
  memoryview, some numeric types). Complex objects need serialization.
```

Sub-interpreters are ~100x lighter than processes. They're the closest Python analog to Go goroutines: lightweight, parallel, share-nothing by default.

---

## FasterAPI's Concurrency API

FasterAPI provides three concurrency primitives. Use the right one for your workload:

### `run_in_subinterpreter(func, *args)` — CPU-bound work

```python
from FasterAPI.concurrency import run_in_subinterpreter

async def compute_hash(data: bytes) -> str:
    return await run_in_subinterpreter(hashlib.sha256, data)
```

**What happens under the hood:**

| Python Version | Backend | Behavior |
|---|---|---|
| 3.13+ (with `interpreters`) | Sub-interpreter pool | Own GIL, true parallelism, no pickling |
| 3.13+ (without `interpreters`) | ProcessPoolExecutor | Separate process, pickle-based |
| 3.10–3.12 | ProcessPoolExecutor | Separate process, pickle-based |

**When to use:**

- CPU-intensive computation (hashing, image processing, data crunching)
- Work that would block the event loop for >1ms
- Compute tasks that don't need shared mutable state

**When NOT to use:**

- I/O-bound work (database queries, HTTP calls) — use `async`/`await` instead
- Tasks that need access to the main interpreter's global state
- Very short computations (<0.1ms) — the dispatch overhead isn't worth it

### `run_in_threadpool(func, *args)` — Blocking I/O

```python
from FasterAPI.concurrency import run_in_threadpool

async def read_legacy_file(path: str) -> bytes:
    return await run_in_threadpool(open(path, "rb").read)
```

**When to use:**

- Calling synchronous libraries that do I/O (file reads, legacy database drivers)
- Wrapping blocking SDK calls that don't have async versions
- Any blocking operation that would freeze the event loop

**When NOT to use:**

- CPU-bound work — threads share the GIL, so you get zero parallelism
- Operations that already have async versions — just `await` them directly

### `run_in_executor(func, *args)` — Process pool

```python
from FasterAPI.concurrency import run_in_executor

async def heavy_computation(n: int) -> int:
    return await run_in_executor(sum, range(n))
```

**When to use:**

- CPU-bound work on Python < 3.13
- Functions with arguments that are picklable
- When you explicitly want process isolation

**When NOT to use:**

- Arguments that can't be pickled (open file handles, database connections, lambdas)
- On Python 3.13+ — prefer `run_in_subinterpreter` instead

---

## Decision Flowchart

```
Is the work CPU-bound or I/O-bound?
│
├── I/O-bound
│   │
│   ├── Has async API?  →  Just use await
│   └── No async API?   →  run_in_threadpool()
│
└── CPU-bound
    │
    ├── Python 3.13+ with interpreters module?
    │   └──  run_in_subinterpreter()    ← best option
    │
    ├── Arguments picklable?
    │   └──  run_in_subinterpreter()    ← falls back to ProcessPool
    │
    └── Arguments not picklable?
        └──  Restructure to pass serializable data,
             or run_in_threadpool() if parallelism isn't critical
```

---

## SubInterpreterPool Internals

### Pool initialization

```python
pool = SubInterpreterPool(max_workers=4)
```

On first `.run()` call (lazy init):

- Creates `max_workers` sub-interpreters via `interpreters.create()`
- Creates a `ThreadPoolExecutor` with the same number of workers
- Creates an `asyncio.Semaphore(max_workers)` to limit concurrency

### How a task executes

```
1. await pool.run(func, *args)
2. Acquire semaphore (limits concurrent sub-interpreter tasks)
3. Select interpreter via round-robin: id(current_task) % pool_size
4. Submit to ThreadPoolExecutor: interp.call(func, *args)
5. Thread runs func in the sub-interpreter (with its own GIL)
6. Result returned to the awaiting coroutine
```

```
Main event loop thread          Thread pool threads
─────────────────────          ─────────────────────
await pool.run(f, x)
  │
  ├─ acquire semaphore
  ├─ submit to executor ──────→ Thread 1: interp_0.call(f, x)
  │                              (runs with interp_0's GIL)
  │   (event loop continues      │
  │    serving other requests)    │
  │                               ▼
  ├─ result ready ◄──────────── return value
  └─ return result
```

### Fallback pool (no `interpreters` module)

When the `interpreters` module isn't available, `SubInterpreterPool` is replaced with a drop-in that uses `ProcessPoolExecutor`:

```python
class SubInterpreterPool:  # fallback
    def __init__(self, max_workers=None):
        self._executor = ProcessPoolExecutor(max_workers=max_workers or cpu_count)

    async def run(self, func, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, partial(func, *args))
```

Same API, different backend. Your code doesn't change.

---

## Examples

### Image Thumbnail Generation

```python
from PIL import Image
import io
from FasterAPI.concurrency import run_in_subinterpreter

def generate_thumbnail(image_bytes: bytes, size: tuple[int, int]) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail(size)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

@app.post("/upload")
async def upload_image(file: UploadFile):
    data = await file.read()
    thumb = await run_in_subinterpreter(generate_thumbnail, data, (128, 128))
    return Response(content=thumb, media_type="image/jpeg")
```

### CPU-Bound Data Processing

```python
import hashlib
from FasterAPI.concurrency import run_in_subinterpreter

def compute_proof_of_work(data: bytes, difficulty: int) -> tuple[int, str]:
    nonce = 0
    target = "0" * difficulty
    while True:
        attempt = hashlib.sha256(data + nonce.to_bytes(8, "big")).hexdigest()
        if attempt.startswith(target):
            return nonce, attempt
        nonce += 1

@app.post("/mine")
async def mine_block(data: bytes):
    nonce, hash_val = await run_in_subinterpreter(compute_proof_of_work, data, 4)
    return {"nonce": nonce, "hash": hash_val}
```

### Mixed I/O and CPU

```python
@app.get("/report/{id}")
async def generate_report(id: str):
    # I/O-bound: fetch from database (runs on event loop)
    raw_data = await db.fetch(f"SELECT * FROM reports WHERE id = $1", id)

    # CPU-bound: crunch the numbers (runs in sub-interpreter)
    summary = await run_in_subinterpreter(analyze_data, raw_data)

    # I/O-bound: cache the result (runs on event loop)
    await cache.set(f"report:{id}", summary, ttl=3600)

    return summary
```

---

## Limitations & Caveats

1. **Module state is NOT shared.** Each sub-interpreter has its own import state. Global variables in one interpreter are invisible to others.

2. **Not all types are shareable.** Complex objects (class instances, open connections, file handles) can't be passed directly. Pass bytes, numbers, or strings.

3. **C extensions must be compatible.** Some C extensions aren't safe to use in sub-interpreters. If a function crashes in a sub-interpreter, try `run_in_executor` instead.

4. **The `interpreters` module is experimental** in Python 3.13. It may change or be absent in some builds. FasterAPI always has a working fallback.

5. **Pool sizing matters.** Default is `os.cpu_count()`. For mixed workloads, you may want fewer sub-interpreter workers to leave cores free for the event loop.

---

## Version Compatibility Matrix

| Python | Sub-interpreters | uvloop | Best CPU strategy |
|---|---|---|---|
| 3.10 | No | Yes | ProcessPoolExecutor |
| 3.11 | No | Yes | ProcessPoolExecutor |
| 3.12 | C API only | Yes (via policy) | ProcessPoolExecutor |
| 3.13 | Experimental | Yes (via policy) | SubInterpreterPool (if available) |
| 3.14+ | Expected stable | TBD | SubInterpreterPool |
