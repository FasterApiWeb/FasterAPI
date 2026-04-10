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
| `stage` | Integration / pre-release | **Nobody** — merge from `dev` via PR only |
| `dev` / `dev/*` | Feature integration and branch-level previews | Maintainers via PR only |

For **security-sensitive** reports, use the process in [SECURITY.md](SECURITY.md) instead of a public issue.

### Rules

1. **Never push directly to `master`, `stage`, or `dev`.**
2. Create your branch from **`stage`** (never from an outdated `master` without syncing):
   ```bash
   git checkout stage
   git pull origin stage
   git checkout -b dev/my-feature
   ```
3. Commit with **clear messages** (what changed and why in one line; optional scope prefix, e.g. `docs:`, `bench:`).
4. Open a **pull request from your branch → `dev`** for first integration.
5. CI (tests on Python 3.10–3.13 + benchmarks on PRs) must pass.
6. At least **one approval** is required before merging to `stage`, when reviewers are available.
7. Periodically, maintainers promote `dev` → `stage` and `stage` → `master`.
8. **Stable releases** are **git tags** on `master` (`v0.2.0`, …), which trigger PyPI + Docker + GitHub Releases. The **PyPI version is taken from the tag** (see `hatch-vcs` in `pyproject.toml`) — **do not** rely on editing a static `version =` in `pyproject.toml` for releases.
9. To automate semver tagging, add exactly one PR label: `release:patch`, `release:minor`, or `release:major`. On merge:
   - to `master`: creates `vX.Y.Z`
   - to `stage`: creates `stage-vX.Y.Z`
   - to `dev`: creates `dev-vX.Y.Z`
10. Channel builds publish automatically:
   - `dev` push: TestPyPI `0.0.0.devN`
   - `stage` push: TestPyPI `0.0.0aN`
   - `master` push: TestPyPI `0.0.0rcN`
   - `vX.Y.Z` tag: stable PyPI + Docker + GitHub Release

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

When you open a PR to `dev`, `stage`, or `master`, two workflows run automatically:

1. **CI** — Tests on Python 3.10, 3.11, 3.12, 3.13 with coverage
2. **Benchmark** — Runs framework benchmarks and posts a comparison comment on the PR

The benchmark comment shows:
- Current req/s for FasterAPI vs FastAPI
- Speedup ratios compared to the README baseline
- 🟢 improved / ⚪ neutral / 🔴 regression indicators

A PR with a 🔴 benchmark regression will need justification before merging.

---

## GitHub UI Setup (Required Once)

Configure these in **Settings → Rules → Rulesets**:

1. **Master ruleset**
   - Target: `master`
   - Block direct pushes
   - Require pull request
   - Require status checks: `CI`, `Benchmark`
   - Restrict allowed source branch for PRs to `stage` only
2. **Stage ruleset**
   - Target: `stage`
   - Block direct pushes
   - Require pull request
   - Require status checks: `CI`, `Benchmark`
   - Restrict allowed source branch for PRs to `dev` only
3. **Dev ruleset**
   - Target: `dev`
   - Block direct pushes
   - Require pull request (even for maintainers, if desired)
   - Require status checks: `CI`, `Benchmark`

Also set **Settings → Actions → General** so workflows can create commits/tags when needed (`Read and write permissions` for `GITHUB_TOKEN`).

---

## Release Process (Maintainers)

1. Merge `stage` → `master` via PR
2. Choose release intent with one label on the PR:
   - `release:patch` / `release:minor` / `release:major`
3. Auto-tag workflow creates the next tag on merge (or tag manually):
   ```bash
   git checkout master
   git pull origin master
   git tag v0.x.0
   git push origin v0.x.0
   ```
4. The release workflow automatically:
   - Runs full test suite
   - Builds wheel + sdist (**version = git tag**, via **hatch-vcs**)
   - Publishes to PyPI (`faster-api-web`)
   - Pushes Docker image to `ghcr.io`
   - Creates a GitHub Release with artifacts

### Notes about branch channel versions

- TestPyPI/PyPI require valid PEP 440 versions.
- Human-readable suffixes like `-stage` or `-dev` are not valid upload versions on PyPI.
- Channel identity is represented with valid semver segments:
  - `dev` channel: `.devN`
  - `stage` channel: `aN`
  - `master` preview channel: `rcN`

---

## Listing on Awesome Python

The [awesome-python](https://github.com/vinta/awesome-python) list has **strict** entry rules (activity, documentation, uniqueness). When the project meets [their CONTRIBUTING criteria](https://github.com/vinta/awesome-python/blob/master/CONTRIBUTING.md), a maintainer can propose a PR under **Web Frameworks** using the **PyPI name** as the title:

```markdown
- [faster-api-web](https://github.com/FasterApiWeb/FasterAPI) - High-performance ASGI web framework; FastAPI-like API with msgspec and radix routing.
```

One project per PR; follow their alphabetical order and description style (ends with a period). If a submission is premature, wait until the repo satisfies **Stable** / **Established** / stars thresholds in their guide.
