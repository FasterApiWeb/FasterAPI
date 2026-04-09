"""Single place to resolve the installed distribution version (matches PyPI / git tags)."""

from __future__ import annotations


def get_version() -> str:
    """Return ``faster-api-web`` version from package metadata (set at build from git tags)."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("faster-api-web")
    except PackageNotFoundError:
        return "0.0.0"
