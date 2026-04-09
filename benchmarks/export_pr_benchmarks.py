#!/usr/bin/env python3
"""Write benchmark JSON files for the PR comment workflow."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from benchmarks.compare import (
    measure_direct_asgi_rps,
    measure_http_rps_three_way,
    measure_routing_ops,
)


def main() -> None:
    cwd = Path.cwd()
    asgi = measure_direct_asgi_rps(iterations=50_000)
    routing = measure_routing_ops()
    http_three, fiber_err = asyncio.run(measure_http_rps_three_way(5_000, 50))

    (cwd / "bench_results.json").write_text(
        json.dumps(http_three, indent=0),
        encoding="utf-8",
    )
    (cwd / "asgi_micro.json").write_text(
        json.dumps(asgi, indent=0),
        encoding="utf-8",
    )
    (cwd / "routing_results.json").write_text(
        json.dumps(routing, indent=0),
        encoding="utf-8",
    )
    warn_path = cwd / "fiber_warn.txt"
    if fiber_err:
        warn_path.write_text(fiber_err, encoding="utf-8")
    elif warn_path.exists():
        warn_path.unlink()


if __name__ == "__main__":
    main()
