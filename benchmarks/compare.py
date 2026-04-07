"""Benchmark: FasterAPI vs FastAPI routing performance.

Run: python benchmarks/compare.py

Measures route registration and resolution throughput using the
radix-tree router. Does not require a running server.
"""

import time

from FasterAPI.router import RadixRouter


def bench_registration(n: int = 10_000) -> float:
    router = RadixRouter()
    start = time.perf_counter()
    for i in range(n):
        router.add_route("GET", f"/api/v1/resource{i}", lambda: None)
    elapsed = time.perf_counter() - start
    return elapsed


def bench_resolution_static(n: int = 100_000) -> float:
    router = RadixRouter()
    for i in range(100):
        router.add_route("GET", f"/api/v1/resource{i}", lambda: None)

    start = time.perf_counter()
    for _ in range(n):
        router.resolve("GET", "/api/v1/resource50")
    elapsed = time.perf_counter() - start
    return elapsed


def bench_resolution_param(n: int = 100_000) -> float:
    router = RadixRouter()
    router.add_route("GET", "/users/{user_id}/posts/{post_id}", lambda: None)

    start = time.perf_counter()
    for _ in range(n):
        router.resolve("GET", "/users/42/posts/99")
    elapsed = time.perf_counter() - start
    return elapsed


if __name__ == "__main__":
    print("FasterAPI Router Benchmark")
    print("=" * 40)

    t = bench_registration()
    print(f"Register 10k routes:   {t*1000:.1f}ms")

    t = bench_resolution_static()
    print(f"Resolve static 100k:   {t*1000:.1f}ms ({100_000/t:.0f} ops/s)")

    t = bench_resolution_param()
    print(f"Resolve param 100k:    {t*1000:.1f}ms ({100_000/t:.0f} ops/s)")
