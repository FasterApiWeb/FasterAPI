# Python 3.13 and compatibility

All **tutorials and examples** in this documentation are written for **Python 3.13**: that is the
version we recommend for new projects and what CI uses as the primary interpreter.

## Install the `faster-api-web` package

Everything starts from PyPI — the distribution name is **`faster-api-web`**:

```bash
pip install faster-api-web
```

Imports use the **`FasterAPI`** package name in code (`from FasterAPI import Faster`).

## Why 3.13 first

- **Better asyncio** performance and ongoing runtime improvements.
- **Sub-interpreters** (where available) for CPU-bound work with a model closer to multiple GILs;
  see the main README and [Benchmarks](benchmarks.md) for details.

## Fallbacks (3.10, 3.11, 3.12)

The project supports **`requires-python >= 3.10`**. On older versions:

| Area | Behaviour on 3.10–3.12 |
|------|-------------------------|
| **CPU-bound helpers** | Falls back to **process pool** (and similar) instead of sub-interpreters where 3.13 APIs are unavailable. |
| **uvloop** | Still recommended on Linux for I/O-heavy apps; optional everywhere. |
| **Syntax in docs** | Examples use modern syntax (e.g. `list[str]`, `str \| None`) that works on 3.10+ with normal imports; on **3.10** you may need `from __future__ import annotations` in some files. |

If something behaves differently on an older interpreter, open an issue with your **exact Python version**.
