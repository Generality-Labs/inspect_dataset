"""In task mode, the answer-text rules report not_applicable under a non-verbatim scorer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import inspect_dataset.cli as cli_mod
from inspect_dataset._types import FieldMap
from inspect_dataset.cli import cli

_RECORDS = [
    {"input": f"Question {i}?", "target": target, "id": f"s{i}"}
    for i, target in enumerate(["def solve(x):\n    return x * 2 + 1", "yes", "no", "Maybe."])
]


def _scan_summary(tmp_path: Path, monkeypatch, scorers: list[str]) -> dict:
    def fake_load_task_from_spec(spec, limit=None, source_info=None):
        fields = FieldMap(question="input", answer="target", id="id", scorers=scorers)
        return [dict(r) for r in _RECORDS], fields

    monkeypatch.setattr(cli_mod, "load_task_from_spec", fake_load_task_from_spec)
    out = tmp_path / "findings"
    args = ["scan", "some.module@t", "-o", str(out)]
    args += ["--scanners", "answer_length,inconsistent_format"]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    return json.loads((out / "scan_summary.json").read_text())


def test_code_execution_scorer_reports_reasons(tmp_path: Path, monkeypatch):
    summary = _scan_summary(tmp_path, monkeypatch, ["inspect_evals/humaneval_scorer"])
    assert summary["scanner_status"] == {
        name: {
            "status": "not_applicable",
            "reason": (
                f"{name} assumes a scorer that compares answer text verbatim; "
                "this task scores with inspect_evals/humaneval_scorer"
            ),
        }
        for name in ("answer_length", "inconsistent_format")
    }
    assert summary["by_scanner"] == {}


@pytest.mark.parametrize("scorers", [["inspect_ai/match"], ["inspect_ai/exact", "inspect_ai/f1"]])
def test_verbatim_scorer_runs_the_rules(tmp_path: Path, monkeypatch, scorers):
    summary = _scan_summary(tmp_path, monkeypatch, scorers)
    assert summary["scanner_status"] == {
        "answer_length": {"status": "ran"},
        "inconsistent_format": {"status": "ran"},
    }
    assert summary["by_scanner"]["answer_length"]["total"] == 1
