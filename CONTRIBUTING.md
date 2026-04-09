# Contributing to FasterAPI

Thank you for your interest in contributing! This document explains how we work.

---

## Branch Model

```
  dev/your-feature ──PR──▶ stage ──PR──▶ master
       (yours)           (integration)    (production)
```

| Branch | Purpose | Who can push directly |
|---|---|---|
| `master` | Production-ready code, releases | **Nobody** — merge from `stage` via PR only |
| `stage` | Integration / pre-release | **Maintainer only** (`@EshwarCVS` / `@FasterApiWeb`) |
| `dev/*` | Your feature or bugfix branch | You |

For **security-sensitive** reports, use the process in [SECURITY.md](SECURITY.md) instead of a public issue.

### Rules

1. **Never push directly to `master` or `stage`.**
2. Create your branch from **`stage`** (never from an outdated `master` without syncing):
   ```bash
   git checkout stage
   git pull origin stage
   git checkout -b dev/my-feature
   ```
3. Commit with **clear messages** (what changed and why in one line; optional scope prefix, e.g. `docs:`, `bench:`).
4. Open a **pull request from your branch → `stage`** (that is the default integration flow for new code).
5. CI (tests on Python 3.10–3.13 + benchmarks on PRs) must pass.
6. At least **one approval** is required before merging to `stage`, when reviewers are available.
7. Periodically, a maintainer opens a PR from **`stage` → `master`** to cut a release.
8. **Releases** are **git tags** on `master` (`v0.2.0`, …), which trigger PyPI + Docker + GitHub Releases. The **PyPI version is taken from the tag** (see `hatch-vcs` in `pyproject.toml`) — **do not** rely on editing a static `version =` in `pyproject.toml` for releases.
9. If you want a merge to `master` to cut a release automatically, add one label on the `stage` → `master` PR: `release:patch`, `release:minor`, or `release:major`. The auto-tag workflow will create the next `vX.Y.Z` tag from that label.

---

## Development Setup

```bash
# Clone and set up
git clone https://github.com/FasterApiWeb/FasterAPI.git
cd FasterAPI
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest --cov=FasterAPI --cov-fail-under=85

# Lint and types (matches CI on Python 3.13)
ruff format --check FasterAPI tests benchmarks
ruff check FasterAPI tests benchmarks
mypy FasterAPI tests

# Multi-version tests (requires Python 3.11–3.13 on PATH)
tox

# Run benchmarks locally
pip install -e ".[benchmark]"
python benchmarks/compare.py --direct
```

---

## PR Checklist

Before opening a PR, verify:

- [ ] All tests pass: `pytest --cov=FasterAPI --cov-report=term-missing --cov-fail-under=85`
- [ ] No regressions in benchmark speedup ratios
- [ ] New features include tests
- [ ] Code follows existing patterns (`__slots__`, type hints, no unnecessary comments)

---

## What Happens on Your PR

When you open a PR to `stage` or `master`, two workflows run automatically:

1. **CI** — Tests on Python 3.10, 3.11, 3.12, 3.13 with coverage
2. **Benchmark** — Runs framework benchmarks and posts a comparison comment on the PR

The benchmark comment shows:
- Current req/s for FasterAPI vs FastAPI
- Speedup ratios compared to the README baseline
- 🟢 improved / ⚪ neutral / 🔴 regression indicators

A PR with a 🔴 benchmark regression will need justification before merging.

---

## Release Process (Maintainers)

1. Merge `stage` → `master` via PR
2. Tag on master:
   ```bash
   git checkout master
   git pull origin master
   git tag v0.x.0
   git push origin v0.x.0
   ```
3. The release workflow automatically:
   - Runs full test suite
   - Builds wheel + sdist (**version = git tag**, via **hatch-vcs**)
   - Publishes to PyPI (`faster-api-web`)
   - Pushes Docker image to `ghcr.io`
   - Creates a GitHub Release with artifacts

---

## Listing on Awesome Python

The [awesome-python](https://github.com/vinta/awesome-python) list has **strict** entry rules (activity, documentation, uniqueness). When the project meets [their CONTRIBUTING criteria](https://github.com/vinta/awesome-python/blob/master/CONTRIBUTING.md), a maintainer can propose a PR under **Web Frameworks** using the **PyPI name** as the title:

```markdown
- [faster-api-web](https://github.com/FasterApiWeb/FasterAPI) - High-performance ASGI web framework; FastAPI-like API with msgspec and radix routing.
```

One project per PR; follow their alphabetical order and description style (ends with a period). If a submission is premature, wait until the repo satisfies **Stable** / **Established** / stars thresholds in their guide.
