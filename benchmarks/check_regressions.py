#!/usr/bin/env python3
"""Fail if ASGI or routing benchmarks regress below baselines/baseline.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from benchmarks.compare import measure_direct_asgi_rps, measure_routing_ops


def main() -> int:
    base_path = Path(__file__).parent / "baseline.json"
    baseline = json.loads(base_path.read_text(encoding="utf-8"))
    mins = baseline["min_speedup_vs_fastapi"]
    min_route = baseline["min_radix_speedup_vs_regex"]

    asgi = measure_direct_asgi_rps(iterations=25_000)
    routing = measure_routing_ops()

    errors: list[str] = []
    for key, label in [
        ("health", "GET /health"),
        ("users_get", "GET /users/{id}"),
        ("users_post", "POST /users"),
    ]:
        sp = asgi[key]["speedup"]
        need = mins[key]
        if sp + 1e-9 < need:
            errors.append(f"{label}: speedup {sp:.2f}x < floor {need}x")

    if routing["speedup"] + 1e-9 < min_route:
        errors.append(
            f"Routing: radix/regex speedup {routing['speedup']:.2f}x < floor {min_route}x",
        )

    if errors:
        print("Benchmark regression guard FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("Benchmark regression guard OK")
    for key in mins:
        print(f"  {key}: {asgi[key]['speedup']:.2f}x (floor {mins[key]}x)")
    print(f"  routing: {routing['speedup']:.2f}x (floor {min_route}x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
