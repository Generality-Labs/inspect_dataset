"""Tests for save_findings output, particularly scan_summary.json content."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rich.console import Console

from inspect_dataset._types import FieldMap, Finding, ScanRun
from inspect_dataset.report import print_report, save_findings
from inspect_dataset.scanner import run_scanners, run_scanners_async
from inspect_dataset.scanners.answer_distribution import answer_distribution


def _make_run(**kwargs) -> ScanRun:
    return ScanRun(
        dataset_name="owner/ds",
        split="test",
        total_samples=5,
        findings=[
            Finding(
                scanner="answer_length",
                severity="low",
                category="format",
                explanation="Too long",
                sample_index=0,
            )
        ],
        **kwargs,
    )


def test_summary_includes_source_type_hf():
    run = _make_run(source_type="hf", revision=None)
    with tempfile.TemporaryDirectory() as d:
        save_findings(run, Path(d))
        summary = json.loads((Path(d) / "scan_summary.json").read_text())
    assert summary["source_type"] == "hf"
    assert summary["revision"] is None


def test_summary_includes_source_type_inspect_task():
    run = _make_run(source_type="inspect_task", revision=None)
    with tempfile.TemporaryDirectory() as d:
        save_findings(run, Path(d))
        summary = json.loads((Path(d) / "scan_summary.json").read_text())
    assert summary["source_type"] == "inspect_task"


def test_summary_includes_revision():
    run = _make_run(source_type="hf", revision="abc123")
    with tempfile.TemporaryDirectory() as d:
        save_findings(run, Path(d))
        summary = json.loads((Path(d) / "scan_summary.json").read_text())
    assert summary["revision"] == "abc123"


def test_summary_includes_config():
    run = _make_run(source_type="hf", config="dimensions")
    with tempfile.TemporaryDirectory() as d:
        save_findings(run, Path(d))
        summary = json.loads((Path(d) / "scan_summary.json").read_text())
    assert summary["config"] == "dimensions"


def test_summary_config_defaults_to_none():
    run = _make_run(source_type="hf")
    with tempfile.TemporaryDirectory() as d:
        save_findings(run, Path(d))
        summary = json.loads((Path(d) / "scan_summary.json").read_text())
    assert summary["config"] is None


def test_summary_default_source_type():
    """ScanRun with no source_type keyword defaults to 'hf'."""
    run = ScanRun(
        dataset_name="owner/ds",
        split="train",
        total_samples=2,
        findings=[],
    )
    with tempfile.TemporaryDirectory() as d:
        save_findings(run, Path(d))
        summary = json.loads((Path(d) / "scan_summary.json").read_text())
    assert summary["source_type"] == "hf"


def test_summary_records_grouping():
    run = _make_run(group_by="dataset_name", group_by_source="auto")
    with tempfile.TemporaryDirectory() as d:
        save_findings(run, Path(d))
        summary = json.loads((Path(d) / "scan_summary.json").read_text())
        report = (Path(d) / "REPORT.md").read_text()
    assert summary["group_by"] == "dataset_name"
    assert summary["group_by_source"] == "auto"
    assert "**Grouped by:** `dataset_name` (auto)" in report


def test_summary_grouping_defaults_to_none():
    run = _make_run()
    with tempfile.TemporaryDirectory() as d:
        save_findings(run, Path(d))
        summary = json.loads((Path(d) / "scan_summary.json").read_text())
        report = (Path(d) / "REPORT.md").read_text()
    assert summary["group_by"] is None
    assert summary["group_by_source"] is None
    assert "Grouped by" not in report


def test_terminal_header_shows_grouping():
    console = Console(record=True, width=200)
    print_report(_make_run(group_by="subject", group_by_source="option"), console=console)
    assert "Grouped by: subject (option)" in console.export_text()


def test_terminal_header_omits_grouping_when_off():
    console = Console(record=True, width=200)
    print_report(_make_run(), console=console)
    assert "Grouped by" not in console.export_text()


def test_run_scanners_takes_group_by_from_fields():
    records = [{"q": "q", "a": "yes", "s": "x"}]
    run = run_scanners(
        records,
        FieldMap(question="q", answer="a", group="s"),
        [answer_distribution],
        group_by_source="option",
    )
    assert (run.group_by, run.group_by_source) == ("s", "option")


def test_run_scanners_without_group_records_none():
    run = run_scanners([{"q": "q", "a": "yes"}], FieldMap(question="q", answer="a"), [])
    assert (run.group_by, run.group_by_source) == (None, None)


async def test_run_scanners_async_records_group_by():
    records = [{"q": "q", "a": "yes", "s": "x"}]
    run = await run_scanners_async(
        records,
        FieldMap(question="q", answer="a", group="s"),
        [answer_distribution],
        group_by_source="option",
    )
    assert (run.group_by, run.group_by_source) == ("s", "option")


# ---------------------------------------------------------------------------
# samples.json — question and answer are always strings
# ---------------------------------------------------------------------------


def _samples(records: list[dict], fields: FieldMap) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        save_findings(_make_run(), Path(tmp), records=records, fields=fields)
        return json.loads((Path(tmp) / "samples.json").read_text())


def test_samples_keep_string_values():
    samples = _samples([{"q": "What?", "a": "yes", "id": 3}], FieldMap("q", "a", id="id"))
    assert samples == [{"index": 0, "question": "What?", "answer": "yes", "id": 3}]


def test_samples_render_list_and_struct_answers_as_json():
    records = [
        {"q": "Which?", "a": ["4", "four"]},
        {"q": "Which?", "a": {"text": "café", "label": 1}},
    ]
    samples = _samples(records, FieldMap(question="q", answer="a"))
    assert samples[0]["answer"] == '[\n  "4",\n  "four"\n]'
    assert samples[1]["answer"] == '{\n  "text": "café",\n  "label": 1\n}'
    assert all(isinstance(s["answer"], str) for s in samples)


def test_samples_render_numbers_and_missing_values():
    samples = _samples([{"q": 7, "a": None}, {"q": "x"}], FieldMap(question="q", answer="a"))
    assert [(s["question"], s["answer"]) for s in samples] == [("7", ""), ("x", "")]


def test_samples_never_contain_bytes():
    records = [{"q": "Q", "a": [{"bytes": b"\x89PNG\r\n", "path": "x.png"}]}]
    answer = _samples(records, FieldMap(question="q", answer="a"))[0]["answer"]
    assert "PNG" not in answer
    assert json.loads(answer) == [{"bytes": "<6 bytes>", "path": "x.png"}]


def test_samples_keep_scalar_rendering():
    samples = _samples([{"q": "Q", "a": True}, {"q": "Q", "a": 1.5}], FieldMap("q", "a"))
    assert [s["answer"] for s in samples] == ["True", "1.5"]


def test_samples_fall_back_to_str_for_values_json_cannot_encode():
    circular: list = ["x"]
    circular.append(circular)
    records = [{"q": "Q", "a": {(1, 2): "pair"}}, {"q": "Q", "a": circular}]
    samples = _samples(records, FieldMap(question="q", answer="a"))
    assert [s["answer"] for s in samples] == ["{(1, 2): 'pair'}", "['x', [...]]"]
