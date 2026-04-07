"""Profile radix-tree routing vs regex-based routing.

Registers 100 routes (mix of static and parameterized), then performs
1,000,000 lookups under cProfile.

Usage:
    python benchmarks/profile_routing.py
    python benchmarks/profile_routing.py --lookups 500000
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import re
import time
from io import StringIO


# ───────────────────────────────────────────────
#  Regex-based router (baseline comparison)
# ───────────────────────────────────────────────

class RegexRouter:
    """Naive regex router — the typical pre-radix-tree approach."""

    def __init__(self) -> None:
        self._routes: list[tuple[str, re.Pattern, object]] = []

    def add_route(self, method: str, path: str, handler: object) -> None:
        # Convert {param} to named groups
        pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path)
        compiled = re.compile(f"^{pattern}$")
        self._routes.append((method, compiled, handler))

    def resolve(self, method: str, path: str) -> tuple[object, dict[str, str]] | None:
        for route_method, pattern, handler in self._routes:
            if route_method != method:
                continue
            match = pattern.match(path)
            if match:
                return handler, match.groupdict()
        return None


# ───────────────────────────────────────────────
#  Route definitions (shared by both routers)
# ───────────────────────────────────────────────

ROUTES: list[tuple[str, str]] = []

# 50 static routes
for i in range(50):
    ROUTES.append(("GET", f"/api/v1/resource{i}"))

# 30 single-param routes
for i in range(30):
    ROUTES.append(("GET", f"/api/v1/collection{i}/{{item_id}}"))

# 20 multi-param routes
for i in range(20):
    ROUTES.append(("GET", f"/api/v1/org/{{org_id}}/team{i}/{{member_id}}"))

# Lookup targets
LOOKUP_TARGETS = [
    ("GET", "/api/v1/resource25"),                   # static hit
    ("GET", "/api/v1/resource0"),                    # static hit (first)
    ("GET", "/api/v1/resource49"),                   # static hit (last)
    ("GET", "/api/v1/collection15/item-42"),         # single param
    ("GET", "/api/v1/collection0/item-1"),           # single param (first)
    ("GET", "/api/v1/org/org-7/team10/member-99"),   # multi param
    ("GET", "/api/v1/org/org-1/team0/member-1"),     # multi param (first)
    ("GET", "/api/v1/nonexistent"),                   # miss
]


def _dummy_handler() -> None:
    pass


# ───────────────────────────────────────────────
#  Benchmark functions
# ───────────────────────────────────────────────

def bench_radix(lookups: int) -> float:
    from FasterAPI.router import RadixRouter

    router = RadixRouter()
    for method, path in ROUTES:
        router.add_route(method, path, _dummy_handler)

    targets = LOOKUP_TARGETS
    n_targets = len(targets)

    start = time.perf_counter()
    for i in range(lookups):
        method, path = targets[i % n_targets]
        router.resolve(method, path)
    return time.perf_counter() - start


def bench_regex(lookups: int) -> float:
    router = RegexRouter()
    for method, path in ROUTES:
        router.add_route(method, path, _dummy_handler)

    targets = LOOKUP_TARGETS
    n_targets = len(targets)

    start = time.perf_counter()
    for i in range(lookups):
        method, path = targets[i % n_targets]
        router.resolve(method, path)
    return time.perf_counter() - start


def profile_radix(lookups: int) -> str:
    """Run cProfile on radix router lookups, return stats string."""
    from FasterAPI.router import RadixRouter

    router = RadixRouter()
    for method, path in ROUTES:
        router.add_route(method, path, _dummy_handler)

    targets = LOOKUP_TARGETS
    n_targets = len(targets)

    profiler = cProfile.Profile()
    profiler.enable()
    for i in range(lookups):
        method, path = targets[i % n_targets]
        router.resolve(method, path)
    profiler.disable()

    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(20)
    return stream.getvalue()


def profile_regex(lookups: int) -> str:
    """Run cProfile on regex router lookups, return stats string."""
    router = RegexRouter()
    for method, path in ROUTES:
        router.add_route(method, path, _dummy_handler)

    targets = LOOKUP_TARGETS
    n_targets = len(targets)

    profiler = cProfile.Profile()
    profiler.enable()
    for i in range(lookups):
        method, path = targets[i % n_targets]
        router.resolve(method, path)
    profiler.disable()

    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(20)
    return stream.getvalue()


# ───────────────────────────────────────────────
#  Main
# ───────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Profile radix vs regex routing")
    parser.add_argument("--lookups", type=int, default=1_000_000, help="Number of lookups (default: 1000000)")
    args = parser.parse_args()

    lookups = args.lookups

    print("=" * 68)
    print(f"  Routing Profile — {len(ROUTES)} routes, {lookups:,} lookups")
    print("=" * 68)

    # ── Timing comparison ──
    print(f"\n  Timing ({lookups:,} lookups)...\n")

    t_radix = bench_radix(lookups)
    t_regex = bench_regex(lookups)

    ops_radix = lookups / t_radix
    ops_regex = lookups / t_regex
    speedup = ops_radix / ops_regex if ops_regex > 0 else float("inf")

    print(f"  {'Router':<20} {'Time (s)':>12} {'Ops/s':>14} {'Speedup':>10}")
    print(f"  {'─' * 58}")
    print(f"  {'Radix Tree':<20} {t_radix:>12.3f} {ops_radix:>14,.0f} {speedup:>9.2f}x")
    print(f"  {'Regex':<20} {t_regex:>12.3f} {ops_regex:>14,.0f} {'1.00x':>10}")

    # ── cProfile details ──
    print(f"\n{'─' * 68}")
    print("  cProfile: Radix Tree Router")
    print("─" * 68)
    print(profile_radix(min(lookups, 200_000)))

    print(f"{'─' * 68}")
    print("  cProfile: Regex Router")
    print("─" * 68)
    print(profile_regex(min(lookups, 200_000)))


if __name__ == "__main__":
    main()
