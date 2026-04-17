# Changelog

PyPI package **`faster-api-web`** versions match **git tags** on `master`
(see the Release workflow). Runtime `FasterAPI.__version__` comes from installed
package metadata.

## 0.1.2 (2026-04-08)

- Documentation site (MkDocs), migration guide, benchmark methodology, and expanded
  CI gates (coverage ≥ 85%, benchmark floors, Codecov strict upload).
- PR benchmarks now include **HTTP comparison** of FasterAPI, FastAPI, and
  **Go Fiber** (`benchmarks/fiber`).
- **`TestClient`** is loaded lazily so a minimal `pip install faster-api-web` does
  not require **httpx** until you import `TestClient`.

## 0.1.1

- Earlier alpha releases and performance baselines.

---

For the full list of commits, see the
[GitHub releases page](https://github.com/FasterApiWeb/FasterAPI/releases).
