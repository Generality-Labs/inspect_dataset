"""Answer-text scanners on struct- and list-typed answer columns (issue #26).

answer_length and inconsistent_format measure answer text. On a non-scalar answer column they
must report that they did not apply, rather than measuring the Python repr of every row.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import inspect_dataset.cli as cli_mod
from inspect_dataset._types import FieldMap
from inspect_dataset.cli import cli
from inspect_dataset.report import save_findings
from inspect_dataset.scanner import run_scanners
from inspect_dataset.scanners.answer_length import answer_length
from inspect_dataset.scanners.inconsistent_format import inconsistent_format

FIELDS = FieldMap(question="q", answer="a")

LIST_OF_DICTS = [
    {
        "q": f"question {i}",
        "a": [
            {"text": "The people are fat and unathletic.", "label": 0},
            {"text": "The people are very thin and good at running.", "label": 1},
        ],
    }
    for i in range(5)
]

# The shape HuggingFace gives StereoSet's `sentences` column: a struct of parallel lists.
STEREOSET_LIKE = [
    {
        "context": f"Many people live in place {i}.",
        "sentences": {
            "sentence": [
                "The people are fat and unathletic.",
                "The people are very thin and good at running.",
                "Cats have whiskers.",
            ],
            "id": ["a", "b", "c"],
            "labels": [{"label": [0, 0], "human_id": ["x", "y"]}] * 3,
            "gold_label": [0, 1, 2],
        },
        "id": f"row-{i}",
    }
    for i in range(3)
]


def test_list_of_dicts_answer_emits_no_findings_and_is_not_applicable(tmp_path: Path):
    run = run_scanners(LIST_OF_DICTS, FIELDS, [answer_length])
    assert run.findings == []
    status = run.scanner_status["answer_length"]
    assert status["status"] == "not_applicable"
    assert "'a'" in status["reason"]
    assert "list" in status["reason"]

    save_findings(run, tmp_path)
    summary = json.loads((tmp_path / "scan_summary.json").read_text())
    assert summary["scanner_status"]["answer_length"] == status
    assert "answer_length" not in summary["by_scanner"]
    assert not (tmp_path / "answer_length.json").exists()


def test_scalar_answer_column_still_fires_and_is_marked_ran(tmp_path: Path):
    records = [{"q": "q0", "a": "yes"}, {"q": "q1", "a": "one two three four five"}]
    run = run_scanners(records, FIELDS, [answer_length])
    assert len(run.findings) == 1
    assert run.findings[0].explanation == (
        "Answer has 5 words (threshold: 4). Long answers are unlikely to be reproduced "
        "verbatim by exact-match scorers. Answer: 'one two three four five'"
    )
    assert run.scanner_status["answer_length"] == {"status": "ran"}

    save_findings(run, tmp_path)
    summary = json.loads((tmp_path / "scan_summary.json").read_text())
    assert summary["by_scanner"]["answer_length"] == {"total": 1, "high": 0, "medium": 1, "low": 0}
    assert summary["scanner_status"]["answer_length"] == {"status": "ran"}
    rows = json.loads((tmp_path / "answer_length.json").read_text())
    assert set(rows[0]) == {
        "scanner",
        "severity",
        "category",
        "explanation",
        "sample_index",
        "sample_id",
        "line",
        "metadata",
    }


def test_clean_scanner_is_distinguishable_from_not_applicable():
    records = [{"q": "q0", "a": "yes"}, {"q": "q1", "a": "no"}]
    run = run_scanners(records, FIELDS, [answer_length, inconsistent_format])
    assert run.findings == []
    assert run.scanner_status == {
        "answer_length": {"status": "ran"},
        "inconsistent_format": {"status": "ran"},
    }


def test_inconsistent_format_not_applicable_on_struct_answers():
    run = run_scanners(
        STEREOSET_LIKE, FieldMap("context", "sentences", "id"), [inconsistent_format]
    )
    assert run.findings == []
    assert run.scanner_status["inconsistent_format"]["status"] == "not_applicable"
    assert "dict" in run.scanner_status["inconsistent_format"]["reason"]


def _scan_stereoset_like(tmp_path: Path, monkeypatch, extra_args: list[str]):
    def fake_load_hf_dataset(dataset, split="train", revision=None, limit=None, config=None):
        return [dict(r) for r in STEREOSET_LIKE]

    monkeypatch.setattr(cli_mod, "load_hf_dataset", fake_load_hf_dataset)
    out = tmp_path / "findings"
    result = CliRunner().invoke(
        cli,
        [
            "scan",
            "owner/stereoset",
            "--question-field",
            "context",
            "--answer-field",
            "sentences",
            "--id-field",
            "id",
            "--scanners",
            "answer_length,inconsistent_format",
            "-o",
            str(out),
            *extra_args,
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads((out / "scan_summary.json").read_text()), out


def test_cli_struct_answer_marks_length_scanners_not_applicable(tmp_path: Path, monkeypatch):
    summary, _ = _scan_stereoset_like(tmp_path, monkeypatch, [])
    assert summary["total_findings"] == 0
    for name in ("answer_length", "inconsistent_format"):
        assert summary["scanner_status"][name]["status"] == "not_applicable"
        assert "--answer-subfield" in summary["scanner_status"][name]["reason"]


def test_cli_answer_subfield_measures_each_sentence(tmp_path: Path, monkeypatch):
    summary, out = _scan_stereoset_like(tmp_path, monkeypatch, ["--answer-subfield", "sentence"])
    assert summary["scanner_status"]["answer_length"] == {"status": "ran"}
    assert summary["by_scanner"]["answer_length"]["total"] == 3
    rows = json.loads((out / "answer_length.json").read_text())
    assert rows[0]["sample_id"] == "row-0"
    assert rows[0]["metadata"]["answer"] == "The people are very thin and good at running."
    assert rows[0]["metadata"]["answer_subfield"] == "sentence"
