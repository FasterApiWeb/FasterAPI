"""Benchmark: FasterAPI vs FastAPI — identical endpoints, head-to-head comparison.

Starts both frameworks on separate ports, fires concurrent requests with
httpx.AsyncClient, and prints a comparison table with req/s, latency
percentiles, and error rate.

Usage:
    python benchmarks/compare.py
    python benchmarks/compare.py --requests 5000 --concurrency 50
"""

import argparse
import asyncio
import multiprocessing
import os
import socket
import sys
import time
from typing import Any, Optional

import httpx

# Ensure the project root is on sys.path so child processes can import FasterAPI
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ───────────────────────────────────────────────
#  App factories (each runs in its own process)
# ───────────────────────────────────────────────

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _run_fasterapi(port: int, ready: multiprocessing.Event) -> None:
    """Launch a FasterAPI (Faster) server in this process."""
    import uvicorn
    import msgspec

    from FasterAPI.app import Faster

    class User(msgspec.Struct):
        name: str
        email: str

    app = Faster(openapi_url=None, docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/users/{user_id}")
    async def get_user(user_id: str):
        return {"id": user_id, "name": "test"}

    @app.post("/users")
    async def create_user(user: User):
        return {"name": user.name, "email": user.email}

    ready.set()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


def _run_fastapi(port: int, ready: multiprocessing.Event) -> None:
    """Launch a FastAPI server in this process."""
    import uvicorn
    from fastapi import FastAPI
    from pydantic import BaseModel

    class User(BaseModel):
        name: str
        email: str

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/users/{user_id}")
    async def get_user(user_id: str):
        return {"id": user_id, "name": "test"}

    @app.post("/users")
    async def create_user(user: User):
        return {"name": user.name, "email": user.email}

    ready.set()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


# ───────────────────────────────────────────────
#  Benchmark runner
# ───────────────────────────────────────────────

async def _wait_for_server(url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return
            except httpx.ConnectError:
                pass
            await asyncio.sleep(0.1)
    raise TimeoutError(f"Server at {url} did not start in {timeout}s")


async def _benchmark_endpoint(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    total: int,
    concurrency: int,
    json_body: Optional[dict] = None,
) -> dict[str, Any]:
    latencies: list[float] = []
    errors = 0
    semaphore = asyncio.Semaphore(concurrency)

    async def _fire() -> None:
        nonlocal errors
        async with semaphore:
            start = time.perf_counter()
            try:
                if method == "GET":
                    resp = await client.get(path)
                else:
                    resp = await client.post(path, json=json_body)
                if resp.status_code >= 400:
                    errors += 1
            except Exception:
                errors += 1
                return
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)

    wall_start = time.perf_counter()
    await asyncio.gather(*[_fire() for _ in range(total)])
    wall_elapsed = time.perf_counter() - wall_start

    if not latencies:
        return {"rps": 0, "p50": 0, "p95": 0, "p99": 0, "errors": errors, "wall": wall_elapsed}

    latencies.sort()
    n = len(latencies)
    return {
        "rps": total / wall_elapsed,
        "p50": latencies[int(n * 0.50)] * 1000,
        "p95": latencies[int(n * 0.95)] * 1000,
        "p99": latencies[int(n * 0.99)] * 1000,
        "errors": errors,
        "wall": wall_elapsed,
    }


async def _run_all_benchmarks(
    base_url: str, total: int, concurrency: int,
) -> dict[str, dict[str, Any]]:
    body = {"name": "Alice", "email": "alice@test.com"}
    results = {}
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # Warmup
        await _benchmark_endpoint(client, "GET", "/health", min(200, total), min(20, concurrency))
        await _benchmark_endpoint(client, "GET", "/users/1", min(200, total), min(20, concurrency))
        await _benchmark_endpoint(client, "POST", "/users", min(200, total), min(20, concurrency), body)
        # Actual benchmarks
        results["health"] = await _benchmark_endpoint(client, "GET", "/health", total, concurrency)
        results["users_get"] = await _benchmark_endpoint(client, "GET", "/users/42", total, concurrency)
        results["users_post"] = await _benchmark_endpoint(client, "POST", "/users", total, concurrency, body)
    return results


# ───────────────────────────────────────────────
#  Comparison table
# ───────────────────────────────────────────────

def _print_header(total: int, concurrency: int) -> None:
    print()
    print("=" * 78)
    print(f"  FasterAPI vs FastAPI — {total:,} requests, {concurrency} concurrent")
    print("=" * 78)


def _print_table(label: str, faster: dict, fastapi: dict) -> None:
    speedup = faster["rps"] / fastapi["rps"] if fastapi["rps"] > 0 else float("inf")
    print(f"\n  {label}")
    print(f"  {'─' * 72}")
    print(f"  {'Metric':<20} {'FasterAPI':>14} {'FastAPI':>14} {'Speedup':>12}")
    print(f"  {'─' * 72}")
    print(f"  {'Req/s':<20} {faster['rps']:>14,.0f} {fastapi['rps']:>14,.0f} {speedup:>11.2f}x")
    print(f"  {'p50 latency (ms)':<20} {faster['p50']:>14.2f} {fastapi['p50']:>14.2f}")
    print(f"  {'p95 latency (ms)':<20} {faster['p95']:>14.2f} {fastapi['p95']:>14.2f}")
    print(f"  {'p99 latency (ms)':<20} {faster['p99']:>14.2f} {fastapi['p99']:>14.2f}")
    print(f"  {'Errors':<20} {faster['errors']:>14} {fastapi['errors']:>14}")


def _print_summary(faster_results: dict, fastapi_results: dict) -> None:
    print()
    print("  Summary")
    print(f"  {'─' * 72}")
    for endpoint, label in [
        ("health", "GET /health"),
        ("users_get", "GET /users/{id}"),
        ("users_post", "POST /users"),
    ]:
        f = faster_results[endpoint]
        fa = fastapi_results[endpoint]
        speedup = f["rps"] / fa["rps"] if fa["rps"] > 0 else float("inf")
        print(f"  {label:<30} {speedup:>6.2f}x faster  "
              f"({f['rps']:,.0f} vs {fa['rps']:,.0f} req/s)")
    print()
    print("  Note: For Fiber (Go) comparison, use wrk/bombardier against")
    print("  a Fiber app on the same machine. Typical Fiber numbers are")
    print("  50,000-120,000 req/s. FasterAPI aims for comparable Python")
    print("  throughput using uvloop + msgspec + radix routing.")
    print()
    print("=" * 78)
    print()


# ───────────────────────────────────────────────
#  Main
# ───────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FasterAPI vs FastAPI benchmark")
    parser.add_argument("--requests", type=int, default=10_000)
    parser.add_argument("--concurrency", type=int, default=100)
    args = parser.parse_args()

    total = args.requests
    concurrency = args.concurrency

    port_faster = _find_free_port()
    port_fastapi = _find_free_port()

    ready_faster = multiprocessing.Event()
    ready_fastapi = multiprocessing.Event()

    proc_faster = multiprocessing.Process(
        target=_run_fasterapi, args=(port_faster, ready_faster), daemon=True,
    )
    proc_fastapi = multiprocessing.Process(
        target=_run_fastapi, args=(port_fastapi, ready_fastapi), daemon=True,
    )

    proc_faster.start()
    proc_fastapi.start()

    try:
        ready_faster.wait(timeout=10)
        ready_fastapi.wait(timeout=10)

        base_faster = f"http://127.0.0.1:{port_faster}"
        base_fastapi = f"http://127.0.0.1:{port_fastapi}"

        asyncio.run(_wait_for_server(f"{base_faster}/health"))
        asyncio.run(_wait_for_server(f"{base_fastapi}/health"))

        _print_header(total, concurrency)

        print("\n  Running FasterAPI benchmarks...", flush=True)
        faster_results = asyncio.run(_run_all_benchmarks(base_faster, total, concurrency))

        print("  Running FastAPI benchmarks...", flush=True)
        fastapi_results = asyncio.run(_run_all_benchmarks(base_fastapi, total, concurrency))

        _print_table("GET /health — simple JSON response", faster_results["health"], fastapi_results["health"])
        _print_table("GET /users/{id} — path parameter extraction", faster_results["users_get"], fastapi_results["users_get"])
        _print_table("POST /users — JSON body parsing & validation", faster_results["users_post"], fastapi_results["users_post"])

        _print_summary(faster_results, fastapi_results)

    finally:
        proc_faster.terminate()
        proc_fastapi.terminate()
        proc_faster.join(timeout=3)
        proc_fastapi.join(timeout=3)


if __name__ == "__main__":
    main()
