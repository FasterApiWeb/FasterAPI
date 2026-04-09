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
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

# Ensure the project root is on sys.path so child processes can import FasterAPI
# httpx is imported lazily inside HTTP benchmark paths so `check_regressions` can run with dev-only deps.
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


def _fiber_binary_path() -> str | None:
    name = "fiberbench.exe" if os.name == "nt" else "fiberbench"
    p = os.path.join(_PROJECT_ROOT, "benchmarks", "fiber", name)
    return p if os.path.isfile(p) else None


def _run_fasterapi(port: int, ready: multiprocessing.Event) -> None:
    """Launch a FasterAPI (Faster) server in this process."""
    import msgspec
    import uvicorn
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
    import httpx

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
    client: "httpx.AsyncClient",
    method: str,
    path: str,
    total: int,
    concurrency: int,
    json_body: dict | None = None,
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


async def measure_http_rps_three_way(
    total: int,
    concurrency: int,
    fiber_executable: str | None = None,
) -> tuple[dict[str, dict[str, float]], str | None]:
    """Run the same HTTP load against FasterAPI, FastAPI, and (optional) Go Fiber."""
    fiber_exe = fiber_executable or _fiber_binary_path()
    port_faster = _find_free_port()
    port_fastapi = _find_free_port()
    port_fiber = _find_free_port()
    if fiber_exe and port_fiber in (port_faster, port_fastapi):
        port_fiber = _find_free_port()

    ready_faster = multiprocessing.Event()
    ready_fastapi = multiprocessing.Event()

    proc_faster = multiprocessing.Process(
        target=_run_fasterapi,
        args=(port_faster, ready_faster),
        daemon=True,
    )
    proc_fastapi = multiprocessing.Process(
        target=_run_fastapi,
        args=(port_fastapi, ready_fastapi),
        daemon=True,
    )
    proc_fiber: subprocess.Popen | None = None
    if fiber_exe:
        env = os.environ.copy()
        env["PORT"] = str(port_fiber)
        proc_fiber = subprocess.Popen(
            [fiber_exe],
            env=env,
            cwd=os.path.join(_PROJECT_ROOT, "benchmarks", "fiber"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    proc_faster.start()
    proc_fastapi.start()

    fiber_err: str | None = None
    try:
        ready_faster.wait(timeout=15)
        ready_fastapi.wait(timeout=15)

        base_faster = f"http://127.0.0.1:{port_faster}"
        base_fastapi = f"http://127.0.0.1:{port_fastapi}"

        await _wait_for_server(f"{base_faster}/health")
        await _wait_for_server(f"{base_fastapi}/health")

        if proc_fiber:
            try:
                await _wait_for_server(f"http://127.0.0.1:{port_fiber}/health")
            except TimeoutError as e:
                fiber_err = str(e)
                proc_fiber.terminate()
                proc_fiber = None

        faster_res = await _run_all_benchmarks(base_faster, total, concurrency)
        fastapi_res = await _run_all_benchmarks(base_fastapi, total, concurrency)
        fiber_res: dict[str, dict[str, Any]] = {}
        if proc_fiber:
            fiber_res = await _run_all_benchmarks(
                f"http://127.0.0.1:{port_fiber}",
                total,
                concurrency,
            )

        out: dict[str, dict[str, float]] = {}
        for key in ("health", "users_get", "users_post"):
            f_rps = float(faster_res[key]["rps"])
            fa_rps = float(fastapi_res[key]["rps"])
            entry: dict[str, float] = {
                "fasterapi": f_rps,
                "fastapi": fa_rps,
                "speedup": f_rps / fa_rps if fa_rps > 0 else 0.0,
            }
            if proc_fiber and key in fiber_res:
                entry["fiber"] = float(fiber_res[key]["rps"])
            out[key] = entry

        return out, fiber_err
    finally:
        proc_faster.terminate()
        proc_fastapi.terminate()
        proc_faster.join(timeout=5)
        proc_fastapi.join(timeout=5)
        if proc_fiber:
            proc_fiber.terminate()
            try:
                proc_fiber.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc_fiber.kill()


async def _run_all_benchmarks(
    base_url: str,
    total: int,
    concurrency: int,
) -> dict[str, dict[str, Any]]:
    import httpx

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
        print(f"  {label:<30} {speedup:>6.2f}x faster  ({f['rps']:,.0f} vs {fa['rps']:,.0f} req/s)")
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


def main(total: int = 10_000, concurrency: int = 100) -> None:

    port_faster = _find_free_port()
    port_fastapi = _find_free_port()

    ready_faster = multiprocessing.Event()
    ready_fastapi = multiprocessing.Event()

    proc_faster = multiprocessing.Process(
        target=_run_fasterapi,
        args=(port_faster, ready_faster),
        daemon=True,
    )
    proc_fastapi = multiprocessing.Process(
        target=_run_fastapi,
        args=(port_fastapi, ready_fastapi),
        daemon=True,
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
        _print_table(
            "GET /users/{id} — path parameter extraction", faster_results["users_get"], fastapi_results["users_get"]
        )
        _print_table(
            "POST /users — JSON body parsing & validation", faster_results["users_post"], fastapi_results["users_post"]
        )

        _print_summary(faster_results, fastapi_results)

    finally:
        proc_faster.terminate()
        proc_fastapi.terminate()
        proc_faster.join(timeout=3)
        proc_fastapi.join(timeout=3)


def _build_asgi_pair():
    """Return (faster_app, fastapi_app) for micro-benchmarks."""
    import msgspec as _msgspec
    from FasterAPI.app import Faster

    class UserF(_msgspec.Struct):
        name: str
        email: str

    fapp = Faster(openapi_url=None, docs_url=None, redoc_url=None)

    @fapp.get("/health")
    async def _fh():
        return {"status": "ok"}

    @fapp.get("/users/{user_id}")
    async def _fg(user_id: str):
        return {"id": user_id, "name": "test"}

    @fapp.post("/users")
    async def _fp(user: UserF):
        return {"name": user.name, "email": user.email}

    try:
        from fastapi import FastAPI
        from pydantic import BaseModel
    except ImportError as e:
        raise RuntimeError("FastAPI/Pydantic required for comparison") from e

    class UserP(BaseModel):
        name: str
        email: str

    faapp = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @faapp.get("/health")
    async def _fah():
        return {"status": "ok"}

    @faapp.get("/users/{user_id}")
    async def _fag(user_id: str):
        return {"id": user_id, "name": "test"}

    @faapp.post("/users")
    async def _fap(user: UserP):
        return {"name": user.name, "email": user.email}

    return fapp, faapp


def measure_direct_asgi_rps(iterations: int = 50_000) -> dict[str, dict[str, float]]:
    """Run direct ASGI benchmark and return req/s and speedup (for CI guards)."""
    import json as _json

    fapp, faapp = _build_asgi_pair()
    N = iterations

    async def _make_scope(method: str, path: str, body: dict | None = None):
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"host", b"localhost"),
            ],
            "client": ("127.0.0.1", 9999),
        }
        body_bytes = _json.dumps(body).encode() if body else b""
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        async def send(msg: dict):
            sent.append(msg)

        return scope, receive, send

    async def _bench(app, method: str, path: str, body=None) -> float:
        for _ in range(200):
            s, r, sn = await _make_scope(method, path, body)
            await app(s, r, sn)
        start = time.perf_counter()
        for _ in range(N):
            s, r, sn = await _make_scope(method, path, body)
            await app(s, r, sn)
        return N / (time.perf_counter() - start)

    async def _run():
        body = {"name": "Alice", "email": "alice@test.com"}
        out: dict[str, dict[str, float]] = {}
        for key, m, p, b in [
            ("health", "GET", "/health", None),
            ("users_get", "GET", "/users/42", None),
            ("users_post", "POST", "/users", body),
        ]:
            f_rps = await _bench(fapp, m, p, b)
            fa_rps = await _bench(faapp, m, p, b)
            out[key] = {
                "fasterapi": f_rps,
                "fastapi": fa_rps,
                "speedup": f_rps / fa_rps if fa_rps > 0 else 0.0,
            }
        return out

    return asyncio.run(_run())


def measure_routing_ops() -> dict[str, float]:
    """Radix vs regex routing throughput (same workload as CI benchmark)."""
    import re

    from FasterAPI.router import RadixRouter

    router = RadixRouter()
    for i in range(50):
        router.add_route("GET", f"/static/route{i}", lambda: None, {})
    for i in range(30):
        router.add_route("GET", f"/users/{{id}}/action{i}", lambda: None, {})
    for i in range(20):
        router.add_route(
            "GET",
            f"/org/{{org_id}}/team/{{team_id}}/member{i}",
            lambda: None,
            {},
        )

    paths = ["/static/route25", "/users/42/action15", "/org/abc/team/xyz/member10"]
    N = 500_000
    start = time.perf_counter()
    for _ in range(N):
        for p in paths:
            router.resolve("GET", p)
    radix_ops = (N * 3) / (time.perf_counter() - start)

    regex_routes = []
    for i in range(50):
        regex_routes.append((re.compile(f"^/static/route{i}$"), None))
    for i in range(30):
        regex_routes.append(
            (re.compile(r"^/users/(\w+)/action" + str(i) + r"$"), None),
        )
    for i in range(20):
        regex_routes.append(
            (re.compile(r"^/org/(\w+)/team/(\w+)/member" + str(i) + r"$"), None),
        )

    def regex_resolve(path: str):
        for p, h in regex_routes:
            m = p.match(path)
            if m:
                return h, m.groups()
        return None, ()

    start = time.perf_counter()
    for _ in range(N):
        for p in paths:
            regex_resolve(p)
    regex_ops = (N * 3) / (time.perf_counter() - start)

    return {
        "radix": radix_ops,
        "regex": regex_ops,
        "speedup": radix_ops / regex_ops if regex_ops > 0 else 0.0,
    }


def direct_benchmark() -> None:
    """ASGI-level benchmark — no network, no httpx, pure framework speed."""
    try:
        fapp, faapp = _build_asgi_pair()
    except RuntimeError as e:
        print(f"  {e}")
        return

    import json as _json

    N = 50_000

    async def _make_scope(method: str, path: str, body: dict | None = None):
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"host", b"localhost"),
            ],
            "client": ("127.0.0.1", 9999),
        }
        body_bytes = _json.dumps(body).encode() if body else b""
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        async def send(msg: dict):
            sent.append(msg)

        return scope, receive, send

    async def _bench(app, method: str, path: str, body=None) -> float:
        for _ in range(200):
            s, r, sn = await _make_scope(method, path, body)
            await app(s, r, sn)
        start = time.perf_counter()
        for _ in range(N):
            s, r, sn = await _make_scope(method, path, body)
            await app(s, r, sn)
        return N / (time.perf_counter() - start)

    async def _run():
        body = {"name": "Alice", "email": "alice@test.com"}
        print()
        print("=" * 72)
        print(f"  Direct ASGI benchmark — {N:,} requests (no network overhead)")
        print("=" * 72)
        print(f"\n  {'Endpoint':<28} {'FasterAPI':>12} {'FastAPI':>12} {'Speedup':>10}")
        print(f"  {'─' * 66}")
        for label, m, p, b in [
            ("GET /health", "GET", "/health", None),
            ("GET /users/{id}", "GET", "/users/42", None),
            ("POST /users", "POST", "/users", body),
        ]:
            f_rps = await _bench(fapp, m, p, b)
            fa_rps = await _bench(faapp, m, p, b)
            print(f"  {label:<28} {f_rps:>10,.0f}/s {fa_rps:>10,.0f}/s {f_rps / fa_rps:>9.2f}x")
        print()
        print("=" * 72)
        print()

    asyncio.run(_run())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FasterAPI vs FastAPI benchmark")
    parser.add_argument("--requests", type=int, default=10_000)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--direct", action="store_true", help="Run direct ASGI benchmark (no HTTP server)")
    args = parser.parse_args()

    if args.direct:
        direct_benchmark()
    else:
        main(args.requests, args.concurrency)
