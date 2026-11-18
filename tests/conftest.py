from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture
def fake_packages(tmp_path: Path, monkeypatch):
    """Put tmp_path on sys.path and forget any modules imported from it."""
    before = set(sys.modules)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    for name in set(sys.modules) - before:
        module = sys.modules[name]
        locations = [str(getattr(module, "__file__", None)), *getattr(module, "__path__", [])]
        if any(str(tmp_path) in loc for loc in locations):
            del sys.modules[name]
