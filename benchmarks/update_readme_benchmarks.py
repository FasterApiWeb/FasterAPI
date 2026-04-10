from __future__ import annotations

import json
import re
from pathlib import Path


README_PATH = Path("README.md")
BENCH_JSON = Path("bench_results.json")
ROUTING_JSON = Path("routing_results.json")
START_MARKER = "<!-- AUTO_BENCHMARKS_START -->"
END_MARKER = "<!-- AUTO_BENCHMARKS_END -->"


def _load(path: Path) -> dict[str, float]:
    return json.loads(path.read_text(encoding="utf-8"))


def _req(n: float | None) -> str:
    if n is None:
        return "—"
    return f"{round(n):,} req/s"


def render_block() -> str:
    bench = _load(BENCH_JSON)
    routing = _load(ROUTING_JSON)

    rows = {
        "health": "GET /health",
        "users_get": "GET /users/{id}",
        "users_post": "POST /users",
    }

    lines = [
        START_MARKER,
        "",
        "### Auto-updated branch benchmark snapshot (CI)",
        "",
        "| Endpoint | FasterAPI | FastAPI | Speedup |",
        "|---|---|---|---|",
    ]
    for key, label in rows.items():
        item = bench.get(key, {})
        speedup = item.get("speedup")
        speedup_cell = f"**{speedup:.2f}x**" if isinstance(speedup, (int, float)) else "—"
        lines.append(
            f"| `{label}` | **{_req(item.get('fasterapi'))}** | {_req(item.get('fastapi'))} | {speedup_cell} |"
        )

    lines.extend(
        [
            "",
            "| Routing | Radix ops/s | Regex ops/s | Speedup |",
            "|---|---|---|---|",
            f"| 100-route lookup | **{round(routing.get('radix', 0)):,}** | {round(routing.get('regex', 0)):,} | **{routing.get('speedup', 0):.1f}x** |",
            "",
            "_This block is updated automatically on pushes to `dev`, `stage`, and `master`._",
            "",
            END_MARKER,
        ]
    )
    return "\n".join(lines)


def main() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    block = render_block()
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        flags=re.DOTALL,
    )
    if pattern.search(text):
        updated = pattern.sub(block, text)
    else:
        insert_at = text.find("### Framework-Level Benchmark (Direct ASGI)")
        if insert_at == -1:
            raise RuntimeError("README benchmark section not found.")
        updated = text[:insert_at] + block + "\n\n" + text[insert_at:]

    README_PATH.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
