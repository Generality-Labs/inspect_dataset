"""Split and config defaults for HF-mode scans (issue #32).

The ``datasets`` Hub functions are mocked, so no network access is needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import datasets
import pytest
from click.testing import CliRunner

import inspect_dataset.cli as cli_mod
from inspect_dataset.cli import cli
from inspect_dataset.loader import DatasetSelectionError, resolve_hf_split_config

_RECORDS = [
    {"q": "What is 2+2?", "a": "4"},
    {"q": "Capital of France?", "a": "Paris"},
]


def _fake_hub(
    monkeypatch,
    splits: list[str] | None = None,
    configs: list[str] | None = None,
    default_config: str = "default",
) -> list[dict[str, Any]]:
    """Mock the datasets Hub functions and return the list of calls made to them.

    ``configs`` with more than one entry makes ``load_dataset_builder`` fail
    without a config name, as it does for a multi-config dataset with no default.
    """
    calls: list[dict[str, Any]] = []

    def fake_load_dataset_builder(path, name=None, revision=None, **kwargs):
        calls.append(
            {"fn": "load_dataset_builder", "path": path, "name": name, "revision": revision}
        )
        if name is None and configs is not None and len(configs) > 1:
            raise ValueError("Config name is missing.")
        info_splits = dict.fromkeys(splits) if splits is not None else None
        return SimpleNamespace(
            config=SimpleNamespace(name=name or default_config),
            info=SimpleNamespace(splits=info_splits),
        )

    def fake_get_dataset_config_names(path, revision=None, **kwargs):
        calls.append({"fn": "get_dataset_config_names", "path": path, "revision": revision})
        return list(configs or [default_config])

    def fake_get_dataset_split_names(path, config_name=None, revision=None, **kwargs):
        calls.append({"fn": "get_dataset_split_names", "path": path, "revision": revision})
        return list(splits or [])

    monkeypatch.setattr(datasets, "load_dataset_builder", fake_load_dataset_builder)
    monkeypatch.setattr(datasets, "get_dataset_config_names", fake_get_dataset_config_names)
    monkeypatch.setattr(datasets, "get_dataset_split_names", fake_get_dataset_split_names)
    return calls


def test_single_split_is_used(monkeypatch):
    _fake_hub(monkeypatch, splits=["test"])
    assert resolve_hf_split_config("walledai/XSTest", None, None, None) == (
        "test",
        "default",
        True,
        True,
    )


def test_train_is_chosen_among_several_splits(monkeypatch):
    _fake_hub(monkeypatch, splits=["validation", "train"])
    split, _, split_defaulted, _ = resolve_hf_split_config("EleutherAI/drop", None, None, None)
    assert split == "train"
    assert split_defaulted is True


def test_several_splits_without_train_fail_with_the_list(monkeypatch):
    _fake_hub(monkeypatch, splits=["test", "validation"])
    with pytest.raises(DatasetSelectionError) as exc:
        resolve_hf_split_config("TIGER-Lab/MMLU-Pro", None, None, None)
    assert exc.value.option == "split"
    assert exc.value.choices == ["test", "validation"]
    assert "test, validation" in str(exc.value)


def test_several_configs_fail_with_the_list(monkeypatch):
    _fake_hub(monkeypatch, splits=["test"], configs=["ARC-Challenge", "ARC-Easy"])
    with pytest.raises(DatasetSelectionError) as exc:
        resolve_hf_split_config("allenai/ai2_arc", "test", None, None)
    assert exc.value.option == "config"
    assert exc.value.choices == ["ARC-Challenge", "ARC-Easy"]
    assert "ARC-Challenge, ARC-Easy" in str(exc.value)


def test_unrelated_builder_error_is_not_reported_as_a_config_error(monkeypatch):
    def broken_builder(path, name=None, revision=None, **kwargs):
        raise ValueError("something else went wrong")

    _fake_hub(monkeypatch)
    monkeypatch.setattr(datasets, "load_dataset_builder", broken_builder)
    with pytest.raises(ValueError, match="something else went wrong") as exc:
        resolve_hf_split_config("owner/ds", None, None, None)
    assert not isinstance(exc.value, DatasetSelectionError)


def test_given_config_is_used_to_find_splits(monkeypatch):
    calls = _fake_hub(monkeypatch, splits=["boolean_expressions"], configs=["a", "b"])
    assert resolve_hf_split_config("Joschka/big_bench_hard", None, "a", None) == (
        "boolean_expressions",
        "a",
        True,
        False,
    )
    assert [c["name"] for c in calls if c["fn"] == "load_dataset_builder"] == ["a"]


def test_explicit_split_and_config_skip_resolution(monkeypatch):
    calls = _fake_hub(monkeypatch, splits=["test"])
    assert resolve_hf_split_config("owner/ds", "dev", "main", None) == (
        "dev",
        "main",
        False,
        False,
    )
    assert calls == []


def test_revision_is_passed_to_the_hub(monkeypatch):
    calls = _fake_hub(monkeypatch, splits=["test"], configs=["a", "b"])
    with pytest.raises(DatasetSelectionError):
        resolve_hf_split_config("owner/ds", None, None, "abc123")
    assert calls
    assert all(c["revision"] == "abc123" for c in calls)


def test_builder_without_split_info_falls_back_to_split_names(monkeypatch):
    calls = _fake_hub(monkeypatch, splits=None)
    monkeypatch.setattr(
        datasets, "get_dataset_split_names", lambda path, config_name=None, revision=None: ["test"]
    )
    split, _, _, _ = resolve_hf_split_config("owner/ds", None, None, None)
    assert split == "test"
    assert [c["fn"] for c in calls] == ["load_dataset_builder"]


def _scan(tmp_path: Path, monkeypatch, args: list[str], dataset: str = "owner/ds"):
    loaded: dict[str, Any] = {}

    def fake_load_hf_dataset(dataset, split="train", revision=None, limit=None, config=None):
        loaded.update(split=split, config=config, revision=revision)
        return [dict(r) for r in _RECORDS]

    monkeypatch.setattr(cli_mod, "load_hf_dataset", fake_load_hf_dataset)
    out = tmp_path / "findings"
    result = CliRunner().invoke(
        cli,
        [
            "scan",
            dataset,
            "--question-field",
            "q",
            "--answer-field",
            "a",
            "--scanners",
            "answer_length",
            "-o",
            str(out),
            *args,
        ],
    )
    return result, loaded, out


def test_cli_records_defaulted_split_and_config(tmp_path: Path, monkeypatch):
    _fake_hub(monkeypatch, splits=["test"])
    result, loaded, out = _scan(tmp_path, monkeypatch, [])
    assert result.exit_code == 0, result.output
    assert loaded == {"split": "test", "config": "default", "revision": None}

    summary = json.loads((out / "scan_summary.json").read_text())
    assert summary["split"] == "test"
    assert summary["config"] == "default"
    assert summary["split_defaulted"] is True
    assert summary["config_defaulted"] is True


def test_cli_records_given_split_and_config(tmp_path: Path, monkeypatch):
    calls = _fake_hub(monkeypatch, splits=["test"])
    result, loaded, out = _scan(tmp_path, monkeypatch, ["--split", "dev", "--config", "main"])
    assert result.exit_code == 0, result.output
    assert calls == []
    assert loaded["split"] == "dev"
    assert loaded["config"] == "main"

    summary = json.loads((out / "scan_summary.json").read_text())
    assert summary["split_defaulted"] is False
    assert summary["config_defaulted"] is False


def test_cli_several_splits_without_train_names_split_option(tmp_path: Path, monkeypatch):
    _fake_hub(monkeypatch, splits=["test", "validation"])
    result, loaded, _ = _scan(tmp_path, monkeypatch, [], dataset="TIGER-Lab/MMLU-Pro")
    assert result.exit_code == 2
    assert "--split" in result.output
    assert "test, validation" in result.output
    assert loaded == {}


def test_cli_several_configs_names_config_option(tmp_path: Path, monkeypatch):
    _fake_hub(monkeypatch, splits=["test"], configs=["ARC-Challenge", "ARC-Easy"])
    result, loaded, _ = _scan(tmp_path, monkeypatch, [], dataset="allenai/ai2_arc")
    assert result.exit_code == 2
    assert "--config" in result.output
    assert "ARC-Challenge, ARC-Easy" in result.output
    assert "load_dataset(" not in result.output
    assert loaded == {}


def test_cli_task_mode_records_null_split_and_defaulted_flags(tmp_path: Path, monkeypatch):
    def fake_load_task_from_spec(spec, limit=None):
        from inspect_dataset._types import FieldMap

        return [dict(r) for r in _RECORDS], FieldMap(question="q", answer="a")

    monkeypatch.setattr(cli_mod, "load_task_from_spec", fake_load_task_from_spec)
    out = tmp_path / "findings"
    result = CliRunner().invoke(
        cli, ["scan", "inspect_dataset/fake_task", "--scanners", "answer_length", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output

    summary = json.loads((out / "scan_summary.json").read_text())
    assert summary["source_type"] == "inspect_task"
    assert summary["split"] is None
    assert summary["split_defaulted"] is None
    assert summary["config_defaulted"] is None
