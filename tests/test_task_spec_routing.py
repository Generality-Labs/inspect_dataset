"""Tests for is_task_spec: routing a DATASET argument to the task or HF loader.

HuggingFace owners such as ``google`` and ``openai`` are also importable Python
packages wherever inspect_ai is installed, so the owner alone must not decide.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

import inspect_dataset.cli as cli_mod
from inspect_dataset.cli import cli
from inspect_dataset.loader import is_task_spec


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


def _no_registry(monkeypatch):
    def fail(type, name):
        raise AssertionError(f"registry consulted for {name!r}")

    monkeypatch.setattr("inspect_ai._util.registry.registry_lookup", fail)


def test_at_sign_is_task():
    assert is_task_spec("inspect_evals.gpqa@gpqa_diamond")
    assert is_task_spec("path/to/task.py@task_fn")


def test_no_slash_is_hf():
    assert not is_task_spec("squad")


def test_owner_not_importable_is_hf_without_registry(monkeypatch):
    _no_registry(monkeypatch)
    assert not is_task_spec("no_such_owner_pkg_xyz/boolq")


def test_owner_with_module_is_task(fake_packages: Path, monkeypatch):
    pkg = fake_packages / "ids_owner_a"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mytask.py").write_text("")
    _no_registry(monkeypatch)
    assert is_task_spec("ids_owner_a/mytask")


def test_owner_without_module_registry_hit_is_task(fake_packages: Path, monkeypatch):
    pkg = fake_packages / "ids_owner_b"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    looked_up: list[tuple[str, str]] = []

    def fake_lookup(type, name):
        looked_up.append((type, name))
        return object() if name == "ids_owner_b/arc_challenge" else None

    monkeypatch.setattr("inspect_ai._util.registry.registry_lookup", fake_lookup)
    assert is_task_spec("ids_owner_b/arc_challenge")
    assert looked_up == [("task", "ids_owner_b/arc_challenge")]
    assert not is_task_spec("ids_owner_b/something_else")


def test_owner_without_module_or_registry_entry_is_hf(fake_packages: Path):
    pkg = fake_packages / "ids_owner_c"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    assert not is_task_spec("ids_owner_c/boolq")


def test_google_namespace_package_is_hf(fake_packages: Path):
    # google is a namespace package wherever inspect_ai is installed.
    (fake_packages / "google").mkdir()
    assert not is_task_spec("google/boolq")


def test_openai_is_hf():
    # openai is a real dependency, so this is the case from the issue as users hit it.
    assert not is_task_spec("openai/gsm8k")


def test_owner_is_plain_module_is_hf(monkeypatch):
    # find_spec("os.x") raises ModuleNotFoundError because os is not a package.
    monkeypatch.setattr("inspect_ai._util.registry.registry_lookup", lambda type, name: None)
    assert not is_task_spec("os/boolq")


def test_dotted_name_is_hf():
    # find_spec("openai.data.v2") imports openai.data, which does not exist.
    assert not is_task_spec("openai/data.v2")


class _EntryPoint:
    def __init__(self, name: str) -> None:
        self.name = name


def test_registry_unavailable_is_hf(fake_packages: Path, monkeypatch):
    pkg = fake_packages / "ids_owner_d"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    monkeypatch.setattr(
        "importlib.metadata.entry_points", lambda group: [_EntryPoint("ids_owner_d")]
    )
    monkeypatch.setitem(sys.modules, "inspect_ai._util.registry", None)
    assert not is_task_spec("ids_owner_d/boolq")


def test_registry_not_imported_without_owner_entry_point(fake_packages: Path, monkeypatch):
    pkg = fake_packages / "ids_owner_e"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    monkeypatch.setattr("importlib.metadata.entry_points", lambda group: [_EntryPoint("other")])
    monkeypatch.delitem(sys.modules, "inspect_ai._util.registry")
    assert not is_task_spec("ids_owner_e/boolq")
    assert "inspect_ai._util.registry" not in sys.modules


def test_cli_scans_google_boolq_from_hub(fake_packages: Path, monkeypatch):
    (fake_packages / "google").mkdir()
    calls: list[str] = []

    def fake_load_hf_dataset(dataset, split="train", revision=None, limit=None, config=None):
        calls.append(dataset)
        return [{"question": "is water wet", "answer": "true"}]

    def fail_load_task(spec, limit=None):
        raise AssertionError(f"routed {spec!r} to the task loader")

    monkeypatch.setattr(cli_mod, "load_hf_dataset", fake_load_hf_dataset)
    monkeypatch.setattr(cli_mod, "load_task_from_spec", fail_load_task)
    out = fake_packages / "findings"
    result = CliRunner().invoke(
        cli,
        ["scan", "google/boolq", "--scanners", "answer_length", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert calls == ["google/boolq"]
    assert json.loads((out / "scan_summary.json").read_text())["source_type"] == "hf"
