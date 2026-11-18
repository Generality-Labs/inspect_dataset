from pathlib import Path

import pytest

from inspect_dataset._ignore import (
    IGNORE_FILE_NAME,
    IgnoreFileError,
    apply_ignores,
    load_ignore_file,
)
from inspect_dataset._types import Finding, ScanRun

GOOD = (
    "ignore:\n"
    "  - scanner: duplicate_questions\n"
    "    reason: Several questions share one passage by design.\n"
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / IGNORE_FILE_NAME
    path.write_text(text)
    return path


def _finding(scanner: str) -> Finding:
    return Finding(
        scanner=scanner,
        severity="low",
        category="question_quality",
        explanation="e",
        sample_index=0,
    )


def test_the_file_name():
    assert IGNORE_FILE_NAME == ".inspect-dataset.yaml"


def test_load_maps_scanner_to_reason(tmp_path: Path):
    assert load_ignore_file(_write(tmp_path, GOOD)) == {
        "duplicate_questions": "Several questions share one passage by design."
    }


@pytest.mark.parametrize("text", ["", "# nothing\n", "{}\n", "ignore: []\n"])
def test_an_empty_file_ignores_nothing(tmp_path: Path, text: str):
    assert load_ignore_file(_write(tmp_path, text)) == {}


@pytest.mark.parametrize(
    "text",
    [
        "ignore:\n  - scanner: duplicate_questions\n",  # no reason
        "ignore:\n  - scanner: duplicate_questions\n    reason: '  '\n",  # blank reason
        "ignore:\n  - reason: why\n",  # no scanner
        "ignore:\n  - scanner: a\n    reason: r\n    sample: 3\n",  # unknown entry key
        # listed twice
        "ignore:\n  - scanner: a\n    reason: r\n  - scanner: a\n    reason: again\n",
        "ignore:\n  duplicate_questions: why\n",  # not a list
        "- scanner: a\n  reason: r\n",  # top level is not a mapping
        "ignored:\n  - scanner: a\n    reason: r\n",  # unknown top-level key
        "ignore: [\n",  # does not parse
    ],
)
def test_a_malformed_file_is_an_error(tmp_path: Path, text: str):
    with pytest.raises(IgnoreFileError):
        load_ignore_file(_write(tmp_path, text))


def test_a_missing_reason_names_the_entry(tmp_path: Path):
    text = "ignore:\n  - scanner: a\n    reason: r\n  - scanner: b\n"
    with pytest.raises(IgnoreFileError, match=r"ignore\[1\]"):
        load_ignore_file(_write(tmp_path, text))


def _run() -> ScanRun:
    return ScanRun(
        dataset_name="d",
        split=None,
        total_samples=3,
        findings=[
            _finding("duplicate_questions"),
            _finding("duplicate_questions"),
            _finding("answer_length"),
        ],
        scanner_status={
            "duplicate_questions": {"status": "ran"},
            "answer_length": {"status": "ran"},
            "image_mime_type": {"status": "not_applicable", "reason": "no images"},
        },
    )


def test_an_ignored_scanner_keeps_its_count_and_loses_its_findings():
    run = _run()
    apply_ignores(run, {"duplicate_questions": "by design"})
    assert [f.scanner for f in run.findings] == ["answer_length"]
    assert run.scanner_status["duplicate_questions"] == {
        "status": "ignored",
        "reason": "by design",
        "findings": 2,
    }
    assert run.scanner_status["answer_length"] == {"status": "ran"}


def test_an_ignored_scanner_with_no_findings_records_zero():
    run = _run()
    run.findings = []
    apply_ignores(run, {"answer_length": "r"})
    assert run.scanner_status["answer_length"] == {
        "status": "ignored",
        "reason": "r",
        "findings": 0,
    }


def test_a_not_applicable_scanner_stays_not_applicable():
    run = _run()
    apply_ignores(run, {"image_mime_type": "r"})
    assert run.scanner_status["image_mime_type"] == {
        "status": "not_applicable",
        "reason": "no images",
    }


def test_a_scanner_that_did_not_run_is_left_out():
    run = _run()
    apply_ignores(run, {"llm_answer_check": "r"})
    assert "llm_answer_check" not in run.scanner_status
    assert len(run.findings) == 3
