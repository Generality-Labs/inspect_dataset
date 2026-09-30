"""Scanner requirements: the runner records not_applicable when a declared input is missing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from inspect_dataset import LLMScannerDef, ScannerDef, dataset_scanner
from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import run_scanners, run_scanners_async
from inspect_dataset.scanners import BUILTIN_SCANNER_NAMES, LLM_SCANNER_FACTORIES

FIELDS = FieldMap(question="q", answer="a")
NO_ANSWERS = "no non-empty answers in field 'a'"


class _Recorder:
    """A scanner function that records whether it was called."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, records: list[Record], fields: FieldMap) -> list[Finding]:
        self.calls += 1
        return [Finding("", "low", "format", "x", sample_index=0)]


def _answer_status(answers: list[Any]) -> dict[str, str]:
    scanner = ScannerDef(name="needs_answer", fn=_Recorder(), requires=["answer"])
    records = [{"q": f"question {i}", "a": a} for i, a in enumerate(answers)]
    return run_scanners(records, FIELDS, [scanner]).scanner_status["needs_answer"]


def test_scanner_with_missing_requirement_is_not_called():
    fn = _Recorder()
    scanner = ScannerDef(name="needs_answer", fn=fn, requires=["answer"])
    run = run_scanners([{"q": "question", "a": ""}], FIELDS, [scanner])
    assert fn.calls == 0
    assert run.findings == []
    assert run.scanner_status == {
        "needs_answer": {"status": "not_applicable", "reason": NO_ANSWERS}
    }


def test_scanner_with_met_requirement_runs():
    fn = _Recorder()
    scanner = ScannerDef(name="needs_answer", fn=fn, requires=["answer"])
    run = run_scanners([{"q": "question", "a": "yes"}], FIELDS, [scanner])
    assert fn.calls == 1
    assert run.scanner_status == {"needs_answer": {"status": "ran"}}
    assert [f.scanner for f in run.findings] == ["needs_answer"]


def test_scanner_without_requirements_runs_on_empty_answers():
    fn = _Recorder()
    run = run_scanners([{"q": "question", "a": ""}], FIELDS, [ScannerDef(name="any", fn=fn)])
    assert fn.calls == 1
    assert run.scanner_status == {"any": {"status": "ran"}}


@pytest.mark.parametrize(
    "answers",
    [
        [None, None],
        ["", ""],
        ["   ", "\n\t"],
        [[], {}],
        [None, "", " ", [], {}],
    ],
)
def test_answer_requirement_unmet_when_every_answer_is_empty(answers: list[Any]):
    assert _answer_status(answers) == {"status": "not_applicable", "reason": NO_ANSWERS}


def test_answer_requirement_unmet_when_answer_column_is_absent():
    scanner = ScannerDef(name="needs_answer", fn=_Recorder(), requires=["answer"])
    run = run_scanners([{"q": "question"}], FIELDS, [scanner])
    assert run.scanner_status["needs_answer"]["status"] == "not_applicable"


@pytest.mark.parametrize(
    "answers",
    [
        ["", "  ", "yes"],
        [None, 0],
        [None, False],
        [None, ["a"]],
        [None, {"text": "a"}],
    ],
)
def test_answer_requirement_met_when_any_answer_is_non_empty(answers: list[Any]):
    assert _answer_status(answers) == {"status": "ran"}


def test_image_requirement_unmet_without_image_field():
    scanner = ScannerDef(name="needs_image", fn=_Recorder(), requires=["image"])
    run = run_scanners([{"q": "question", "a": "yes", "img": b"x"}], FIELDS, [scanner])
    assert run.scanner_status["needs_image"] == {
        "status": "not_applicable",
        "reason": "no image field; pass --image-field",
    }


def test_image_requirement_reason_in_task_mode_says_images_are_not_loaded():
    scanner = ScannerDef(name="needs_image", fn=_Recorder(), requires=["image"])
    run = run_scanners(
        [{"q": "question", "a": "yes"}], FIELDS, [scanner], source_type="inspect_task"
    )
    assert run.scanner_status["needs_image"] == {
        "status": "not_applicable",
        "reason": "no image field; task scans do not load images from sample input yet",
    }


def test_image_requirement_unmet_when_every_image_is_none():
    fields = FieldMap(question="q", answer="a", image="img")
    scanner = ScannerDef(name="needs_image", fn=_Recorder(), requires=["image"])
    records = [{"q": "question", "a": "yes", "img": None}, {"q": "question", "a": "yes"}]
    run = run_scanners(records, fields, [scanner])
    assert run.scanner_status["needs_image"] == {
        "status": "not_applicable",
        "reason": "image field 'img' is empty in every row",
    }


def test_image_requirement_met_when_any_image_is_set():
    fields = FieldMap(question="q", answer="a", image="img")
    scanner = ScannerDef(name="needs_image", fn=_Recorder(), requires=["image"])
    records = [{"q": "question", "a": "yes", "img": None}, {"q": "q", "a": "y", "img": b"x"}]
    run = run_scanners(records, fields, [scanner])
    assert run.scanner_status["needs_image"] == {"status": "ran"}


def test_artifacts_requirement(tmp_path: Path):
    scanner = ScannerDef(name="needs_artifacts", fn=_Recorder(), requires=["artifacts"])
    records: list[Record] = [{"q": "question", "a": "yes"}, {"q": "question", "a": "no"}]
    run = run_scanners(records, FIELDS, [scanner])
    assert run.scanner_status["needs_artifacts"] == {
        "status": "not_applicable",
        "reason": "no extraction artifacts; pass --files-root",
    }

    records[1]["__artifacts_dir__"] = str(tmp_path)
    run = run_scanners(records, FIELDS, [scanner])
    assert run.scanner_status["needs_artifacts"] == {"status": "ran"}


def test_first_unmet_requirement_in_declared_order_is_reported():
    scanner = ScannerDef(name="both", fn=_Recorder(), requires=["artifacts", "answer"])
    run = run_scanners([{"q": "question", "a": ""}], FIELDS, [scanner])
    assert run.scanner_status["both"]["reason"] == "no extraction artifacts; pass --files-root"


async def test_llm_scanner_with_missing_requirement_is_not_called():
    calls = 0

    async def _llm(records: list[Record], fields: FieldMap) -> list[Finding]:
        nonlocal calls
        calls += 1
        return []

    scanners = [
        LLMScannerDef(name="llm_needs_answer", fn=_llm, requires=["answer"]),
        ScannerDef(name="sync_needs_answer", fn=_Recorder(), requires=["answer"]),
    ]
    run = await run_scanners_async([{"q": "question", "a": " "}], FIELDS, scanners)
    assert calls == 0
    assert run.scanner_status == {
        "sync_needs_answer": {"status": "not_applicable", "reason": NO_ANSWERS},
        "llm_needs_answer": {"status": "not_applicable", "reason": NO_ANSWERS},
    }


def test_plugin_decorator_declares_requirements():
    calls = 0

    @dataset_scanner(description="needs answers", requires=["answer"])
    def plugin(records: list[Record], fields: FieldMap) -> list[Finding]:
        nonlocal calls
        calls += 1
        return []

    assert plugin.requires == ("answer",)
    run = run_scanners([{"q": "question", "a": None}], FIELDS, [plugin])
    assert calls == 0
    assert run.scanner_status["plugin"] == {"status": "not_applicable", "reason": NO_ANSWERS}


def test_requires_accepts_a_single_name():
    assert ScannerDef(name="s", fn=_Recorder(), requires="image").requires == ("image",)


def test_requires_defaults_to_empty():
    assert ScannerDef(name="s", fn=_Recorder()).requires == ()
    assert dataset_scanner()(_Recorder().__call__).requires == ()


@pytest.mark.parametrize(
    "make",
    [
        lambda: ScannerDef(name="s", fn=_Recorder(), requires=["answers"]),  # type: ignore[list-item]
        lambda: LLMScannerDef(name="s", fn=_Recorder(), requires=["context"]),  # type: ignore[arg-type,list-item]
        lambda: dataset_scanner(requires=["files"]),  # type: ignore[list-item]
    ],
)
def test_unknown_requirement_is_rejected(make: Any):
    with pytest.raises(ValueError, match="unknown scanner requirement"):
        make()


def _llm_requires(name: str) -> tuple[str, ...]:
    return LLM_SCANNER_FACTORIES[name]("mockllm/model").requires


@pytest.mark.parametrize(
    ("name", "requires"),
    [
        ("answer_length", ("answer",)),
        ("inconsistent_format", ("answer",)),
        ("answer_distribution", ("answer",)),
        ("binary_question_ratio", ("answer",)),
        ("forced_choice_leakage", ("answer",)),
        ("markdown_integrity", ("answer",)),
        ("image_mime_type", ("image",)),
        ("text_layer_recall", ("artifacts", "answer")),
        ("numeric_provenance", ("artifacts", "answer")),
        ("duplicate_questions", ()),
        ("encoding_issues", ()),
        ("extraction_artifacts", ()),
    ],
)
def test_builtin_requirements(name: str, requires: tuple[str, ...]):
    assert BUILTIN_SCANNER_NAMES[name].requires == requires


@pytest.mark.parametrize("name", ["label_correctness", "answerability", "ambiguity"])
def test_llm_builtins_require_answers(name: str):
    assert _llm_requires(name) == ("answer",)


def test_builtins_on_a_dataset_without_answers():
    records = [
        {"q": "Is it red or blue?", "a": ""},
        {"q": "Write a poem or a story.", "a": ""},
    ]
    run = run_scanners(records, FIELDS, list(BUILTIN_SCANNER_NAMES.values()))
    assert run.findings == []
    status = {name: s["status"] for name, s in run.scanner_status.items()}
    assert status == {
        "answer_length": "not_applicable",
        "duplicate_questions": "ran",
        "inconsistent_format": "not_applicable",
        "answer_distribution": "not_applicable",
        "forced_choice_leakage": "not_applicable",
        "encoding_issues": "ran",
        "latex_escapes": "ran",
        "mojibake": "ran",
        "binary_question_ratio": "not_applicable",
        "image_mime_type": "not_applicable",
        "markdown_integrity": "not_applicable",
        "extraction_artifacts": "ran",
        "text_layer_recall": "not_applicable",
        "numeric_provenance": "not_applicable",
    }


def test_scanners_command_lists_requirements():
    from click.testing import CliRunner

    from inspect_dataset.cli import cli

    result = CliRunner().invoke(cli, ["scanners"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert "Requires" in next(line for line in lines if "Description" in line)
    assert "artifacts, answer" in next(line for line in lines if "text_layer_recall" in line)
