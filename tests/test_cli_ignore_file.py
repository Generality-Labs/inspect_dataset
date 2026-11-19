import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import inspect_dataset.cli as cli_mod
from inspect_dataset._types import FieldMap
from inspect_dataset.cli import cli

GOOD = (
    "ignore:\n"
    "  - scanner: duplicate_questions\n"
    "    reason: Several questions share one passage by design.\n"
)
RECORDS = [{"q": "Same?", "a": "x"}, {"q": "Same?", "a": "x"}]
HF = [
    "scan",
    "owner/data",
    "--question-field",
    "q",
    "--answer-field",
    "a",
    "--scanners",
    "duplicate_questions",
]
TASK = ["scan", "pkg.mod@my_task", "--scanners", "duplicate_questions"]


@pytest.fixture
def fake_hf(monkeypatch):
    def load(dataset, split="train", revision=None, limit=None, config=None):
        return list(RECORDS)

    def resolve(dataset, split, config, revision):
        return split or "train", config or "default", split is None, config is None

    monkeypatch.setattr(cli_mod, "load_hf_dataset", load)
    monkeypatch.setattr(cli_mod, "resolve_hf_split_config", resolve)


@pytest.fixture
def fake_task(monkeypatch):
    def load(spec, limit=None, source_info=None):
        return list(RECORDS), FieldMap(question="q", answer="a")

    monkeypatch.setattr(cli_mod, "load_task_from_spec", load)


def _summary(out: Path) -> dict:
    return json.loads((out / "scan_summary.json").read_text())


def test_the_option_ignores_a_scanner_and_keeps_its_count(tmp_path, fake_hf):
    ignore = tmp_path / "ignore.yaml"
    ignore.write_text(GOOD)
    out = tmp_path / "out"
    result = CliRunner().invoke(cli, [*HF, "--ignore-file", str(ignore), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert _summary(out)["scanner_status"]["duplicate_questions"] == {
        "status": "ignored",
        "reason": "Several questions share one passage by design.",
        "findings": 1,
    }
    assert _summary(out)["ignore_file"] == str(ignore)
    assert not (out / "duplicate_questions.json").exists()
    assert "Using ignore file" in result.output


def test_an_unknown_scanner_name_warns_and_the_scan_continues(tmp_path, fake_hf):
    ignore = tmp_path / "ignore.yaml"
    ignore.write_text("ignore:\n  - scanner: no_such_scanner\n    reason: r\n")
    out = tmp_path / "out"
    result = CliRunner().invoke(cli, [*HF, "--ignore-file", str(ignore), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "names unknown scanner 'no_such_scanner'" in result.output
    assert _summary(out)["scanner_status"]["duplicate_questions"] == {"status": "ran"}


def test_a_malformed_file_stops_the_scan_before_loading(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("the dataset was loaded")

    monkeypatch.setattr(cli_mod, "load_hf_dataset", fail)
    monkeypatch.setattr(cli_mod, "resolve_hf_split_config", fail)
    ignore = tmp_path / "ignore.yaml"
    ignore.write_text("ignore:\n  - scanner: duplicate_questions\n")
    result = CliRunner().invoke(cli, [*HF, "--ignore-file", str(ignore)])
    assert result.exit_code == 2
    assert str(ignore) in result.output
    assert "reason" in result.output


def test_a_file_in_the_current_directory_is_not_read_for_a_dataset(tmp_path, fake_hf, monkeypatch):
    (tmp_path / ".inspect-dataset.yaml").write_text(GOOD)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out"
    result = CliRunner().invoke(cli, [*HF, "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert _summary(out)["scanner_status"]["duplicate_questions"] == {"status": "ran"}
    assert _summary(out)["ignore_file"] is None


def test_task_mode_uses_the_file_beside_the_task(tmp_path, fake_task, monkeypatch):
    ignore = tmp_path / ".inspect-dataset.yaml"
    ignore.write_text(GOOD)
    monkeypatch.setattr(cli_mod, "find_ignore_file", lambda spec: ignore)
    out = tmp_path / "out"
    result = CliRunner().invoke(cli, [*TASK, "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert _summary(out)["scanner_status"]["duplicate_questions"]["status"] == "ignored"
    assert _summary(out)["ignore_file"] == str(ignore)


def test_the_option_wins_over_the_file_beside_the_task(tmp_path, fake_task, monkeypatch):
    beside = tmp_path / ".inspect-dataset.yaml"
    beside.write_text(GOOD)
    given = tmp_path / "given.yaml"
    given.write_text("ignore: []\n")
    monkeypatch.setattr(cli_mod, "find_ignore_file", lambda spec: beside)
    out = tmp_path / "out"
    result = CliRunner().invoke(cli, [*TASK, "--ignore-file", str(given), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert _summary(out)["scanner_status"]["duplicate_questions"] == {"status": "ran"}
    assert _summary(out)["ignore_file"] == str(given)
