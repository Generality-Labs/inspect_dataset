from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def package_version() -> str:
    """Return the installed inspect-dataset version, or "unknown" without package metadata."""
    try:
        return version("inspect-dataset")
    except PackageNotFoundError:
        return "unknown"
