"""scan_summary.json records the tool version, and in task mode the task spec and scorers."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

from click.testing import CliRunner
from rich.console import Console

import inspect_dataset._version as version_mod
import inspect_dataset.cli as cli_mod
from inspect_dataset._types import FieldMap
from inspect_dataset.cli import cli
from inspect_dataset.report import print_report, save_findings
from inspect_dataset.scanner import LLMScannerDef, run_scanners, run_scanners_async

_RECORDS = [
    {"q": "What is 2+2?", "a": "4"},
    {"q": "Capital of France?", "a": "Paris"},
]

_VERSION = importlib.metadata.version("inspect-dataset")


def _scan(tmp_path: Path, dataset: str, extra_args: list[str] | None = None) -> dict:
    out = tmp_path / "findings"
    result = CliRunner().invoke(cli, ["scan", dataset, "-o", str(out), *(extra_args or [])])
    assert result.exit_code == 0, result.output
    return json.loads((out / "scan_summary.json").read_text())


# ---------------------------------------------------------------------------
# Runner and save_findings
# ---------------------------------------------------------------------------


def test_runner_takes_scorers_from_field_map():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/match"])
    run = run_scanners(list(_RECORDS), fields, [], task="pkg/t", source_type="inspect_task")
    assert run.task == "pkg/t"
    assert run.scorers == ["inspect_ai/match"]


async def test_async_runner_records_task_and_scorers():
    fields = FieldMap(question="q", answer="a", scorers=["x"])
    run = await run_scanners_async(list(_RECORDS), fields, [], task="pkg/t")
    assert run.task == "pkg/t"
    assert run.scorers == ["x"]


def test_runner_defaults_leave_task_and_scorers_unset():
    run = run_scanners(list(_RECORDS), FieldMap(question="q", answer="a"), [])
    assert run.task is None
    assert run.scorers is None


def test_save_findings_writes_version(tmp_path: Path):
    run = run_scanners(list(_RECORDS), FieldMap(question="q", answer="a"), [])
    save_findings(run, tmp_path)
    summary = json.loads((tmp_path / "scan_summary.json").read_text())
    assert summary["version"] == _VERSION
    assert summary["task"] is None
    assert summary["scorers"] is None


def test_version_falls_back_when_metadata_missing(monkeypatch):
    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(version_mod, "version", missing)
    assert version_mod.package_version() == "unknown"


def test_reports_show_version_and_scorers(tmp_path: Path):
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/choice"])
    run = run_scanners(list(_RECORDS), fields, [], task="pkg/t", source_type="inspect_task")
    console = Console(record=True, width=200)
    print_report(run, console=console)
    text = console.export_text()
    assert f"inspect-dataset {_VERSION}" in text
    assert "Scorers: inspect_ai/choice" in text

    save_findings(run, tmp_path)
    report = (tmp_path / "REPORT.md").read_text()
    assert f"**inspect-dataset version:** {_VERSION}" in report
    assert "**Scorers:** `inspect_ai/choice`" in report


# ---------------------------------------------------------------------------
# CLI: HF, task and local modes
# ---------------------------------------------------------------------------


def test_cli_hf_mode_summary(tmp_path: Path, monkeypatch):
    def fake_load_hf_dataset(dataset, split="train", revision=None, limit=None, config=None):
        return [dict(r) for r in _RECORDS]

    monkeypatch.setattr(cli_mod, "load_hf_dataset", fake_load_hf_dataset)
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
    summary = _scan(tmp_path, "owner/ds", ["--question-field", "q", "--answer-field", "a"])
    assert summary["version"] == _VERSION
    assert summary["task"] is None
    assert summary["source"] is None
    assert summary["scorers"] is None


def test_cli_local_mode_summary(tmp_path: Path, monkeypatch):
    def fake_load_local_samples(path, limit=None):
        return [dict(r) for r in _RECORDS], FieldMap(question="q", answer="a")

    monkeypatch.setattr(cli_mod, "load_local_samples", fake_load_local_samples)
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()
    summary = _scan(tmp_path, str(samples_dir))
    assert summary["source_type"] == "local"
    assert summary["version"] == _VERSION
    assert summary["task"] is None
    assert summary["scorers"] is None


_TASK_FILE = """
from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import choice


@task
def tiny():
    return Task(
        dataset=[Sample(input="Pick one", target="A", choices=["x", "y"], id="s1")],
        scorer=choice(),
    )
"""


def test_cli_task_mode_summary(tmp_path: Path):
    task_file = tmp_path / "tiny_task.py"
    task_file.write_text(_TASK_FILE)
    spec = f"{task_file}@tiny"
    summary = _scan(tmp_path, spec)
    assert summary["source_type"] == "inspect_task"
    assert summary["version"] == _VERSION
    assert summary["task"] == spec
    assert summary["scorers"] == ["inspect_ai/choice"]


def test_cli_task_mode_field_override_keeps_scorers(tmp_path: Path, monkeypatch):
    def fake_load_task_from_spec(spec, limit=None, source_info=None):
        records = [{"input": r["q"], "target": r["a"], "id": i} for i, r in enumerate(_RECORDS)]
        fields = FieldMap(question="input", answer="target", id="id", scorers=["inspect_ai/f1"])
        return records, fields

    monkeypatch.setattr(cli_mod, "load_task_from_spec", fake_load_task_from_spec)
    summary = _scan(
        tmp_path, "some.module@t", ["--question-field", "input", "--answer-field", "target"]
    )
    assert summary["task"] == "some.module@t"
    assert summary["scorers"] == ["inspect_ai/f1"]


def test_cli_task_mode_with_llm_scanner_records_task_and_scorers(tmp_path: Path, monkeypatch):
    def fake_load_task_from_spec(spec, limit=None, source_info=None):
        records = [{"input": r["q"], "target": r["a"], "id": i} for i, r in enumerate(_RECORDS)]
        fields = FieldMap(question="input", answer="target", id="id", scorers=["inspect_ai/f1"])
        return records, fields

    async def no_findings(records, fields):
        return []

    monkeypatch.setattr(cli_mod, "load_task_from_spec", fake_load_task_from_spec)
    monkeypatch.setattr(
        cli_mod,
        "LLM_SCANNER_FACTORIES",
        {"fake_llm": lambda model: LLMScannerDef("fake_llm", no_findings)},
    )
    summary = _scan(tmp_path, "some.module@t", ["--model", "mockllm/model"])
    assert summary["scanner_status"]["fake_llm"] == {"status": "ran"}
    assert summary["task"] == "some.module@t"
    assert summary["scorers"] == ["inspect_ai/f1"]
