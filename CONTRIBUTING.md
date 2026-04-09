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

### Rules

1. **Never push directly to `master` or `stage`.**
2. Create your branch from `stage`:
   ```bash
   git checkout stage
   git pull origin stage
   git checkout -b dev/my-feature
   ```
3. Open a PR from your branch → `stage`.
4. CI (tests on Python 3.10–3.13 + benchmarks) must pass.
5. At least 1 approval is required before merging to `stage`.
6. Periodically, the maintainer opens a PR from `stage` → `master` for releases.
7. Releases are tagged on `master` (`v0.2.0`, etc.), which triggers PyPI + Docker publishing.

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
pytest --cov=FasterAPI

# Run benchmarks locally
pip install -e ".[benchmark]"
python benchmarks/compare.py --direct
```

---

## PR Checklist

Before opening a PR, verify:

- [ ] All tests pass: `pytest`
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
   - Builds wheel + sdist
   - Publishes to PyPI (`faster-api-web`)
   - Pushes Docker image to `ghcr.io`
   - Creates a GitHub Release with artifacts
