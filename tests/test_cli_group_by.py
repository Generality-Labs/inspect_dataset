"""CLI tests for grouping the population scanners by subset (issue #36).

Mocks the loaders so no network access or inspect_ai task is needed.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import inspect_dataset.cli as cli_mod
from inspect_dataset.cli import cli

# Two subsets, each always answered the same way: balanced pooled, imbalanced per subset.
_RECORDS = [
    {"q": f"{subset} question {i}", "a": answer, "subset": subset, "subject": subset}
    for subset, answer in [("left", "A"), ("right", "B")]
    for i in range(20)
]


def _run_hf(tmp_path: Path, monkeypatch, extra_args: list[str]):
    monkeypatch.setattr(cli_mod, "load_hf_dataset", lambda *a, **k: [dict(r) for r in _RECORDS])
    monkeypatch.setattr(
        cli_mod,
        "resolve_hf_split_config",
        lambda path, split, config, revision=None: (
            split or "train",
            config,
            split is None,
            config is None,
        ),
    )
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
            "--scanners",
            "answer_distribution",
            "-o",
            str(out),
            *extra_args,
        ],
    )
    return result, out


def _findings(out: Path, scanner: str) -> list[dict]:
    path = out / f"{scanner}.json"
    return json.loads(path.read_text()) if path.exists() else []


def test_group_by_option_groups_and_is_recorded(tmp_path, monkeypatch):
    result, out = _run_hf(tmp_path, monkeypatch, ["--group-by", "subset"])
    assert result.exit_code == 0, result.output
    summary = json.loads((out / "scan_summary.json").read_text())
    assert summary["group_by"] == "subset"
    assert summary["group_by_source"] == "option"
    groups = [f["metadata"]["group"] for f in _findings(out, "answer_distribution")]
    assert groups == ["left", "right"]
    assert "Grouped by: subset (option)" in result.output


def test_hf_mode_does_not_group_automatically(tmp_path, monkeypatch):
    result, out = _run_hf(tmp_path, monkeypatch, [])
    assert result.exit_code == 0, result.output
    summary = json.loads((out / "scan_summary.json").read_text())
    assert summary["group_by"] is None
    assert summary["group_by_source"] is None
    assert _findings(out, "answer_distribution") == []


def test_group_by_unknown_field_is_an_error(tmp_path, monkeypatch):
    result, _ = _run_hf(tmp_path, monkeypatch, ["--group-by", "nope"])
    assert result.exit_code != 0
    assert "nope" in result.output
    assert "--group-by" in result.output
