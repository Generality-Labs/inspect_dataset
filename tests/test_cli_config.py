"""CLI tests for the --config option (multi-config HF datasets).

Mocks the HF loader and split/config resolution so no network access is
needed; verifies that --config is forwarded to load_hf_dataset and persisted
into scan_summary.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import inspect_dataset.cli as cli_mod
from inspect_dataset.cli import cli

_RECORDS = [
    {"q": "What is 2+2?", "a": "4"},
    {"q": "Capital of France?", "a": "Paris"},
]


def _run(tmp_path: Path, monkeypatch, extra_args: list[str]):
    calls: dict[str, object] = {}

    def fake_load_hf_dataset(dataset, split="train", revision=None, limit=None, config=None):
        calls["dataset"] = dataset
        calls["split"] = split
        calls["config"] = config
        return list(_RECORDS)

    def fake_resolve(dataset, split, config, revision):
        return split or "train", config or "default", split is None, config is None

    monkeypatch.setattr(cli_mod, "load_hf_dataset", fake_load_hf_dataset)
    monkeypatch.setattr(cli_mod, "resolve_hf_split_config", fake_resolve)

    out = tmp_path / "findings"
    result = CliRunner().invoke(
        cli,
        [
            "scan",
            "owner/ds",
            "--question-field",
            "q",
            "--answer-field",
            "a",
            "-o",
            str(out),
            *extra_args,
        ],
    )
    return result, calls, out


def test_config_forwarded_and_persisted(tmp_path, monkeypatch):
    result, calls, out = _run(tmp_path, monkeypatch, ["--config", "dimensions"])
    assert result.exit_code == 0, result.output
    assert calls["config"] == "dimensions"

    summary = json.loads((out / "scan_summary.json").read_text())
    assert summary["config"] == "dimensions"
    assert summary["config_defaulted"] is False


def test_config_defaults_to_the_resolved_config(tmp_path, monkeypatch):
    result, calls, out = _run(tmp_path, monkeypatch, [])
    assert result.exit_code == 0, result.output
    assert calls["config"] == "default"

    summary = json.loads((out / "scan_summary.json").read_text())
    assert summary["config"] == "default"
    assert summary["config_defaulted"] is True
