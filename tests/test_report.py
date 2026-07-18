"""Tests for save_findings output, particularly scan_summary.json content."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from inspect_dataset._types import Finding, ScanRun
from inspect_dataset.report import save_findings


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
