"""Per-scanner status: "ran" versus "not_applicable" with a reason."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from inspect_dataset import LLMScannerDef, ScannerDef, ScannerNotApplicable
from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.report import print_report, save_findings
from inspect_dataset.scanner import run_scanners, run_scanners_async

FIELDS = FieldMap(question="q", answer="a")
RECORDS = [{"q": "question", "a": "answer"}]


def _never_applies(records: list[Record], fields: FieldMap) -> list[Finding]:
    raise ScannerNotApplicable("needs --files-root")


def _finds_nothing(records: list[Record], fields: FieldMap) -> list[Finding]:
    return []


NEVER_APPLIES = ScannerDef(name="never_applies", fn=_never_applies)
FINDS_NOTHING = ScannerDef(name="finds_nothing", fn=_finds_nothing)


def test_plugin_scanner_can_report_not_applicable(tmp_path: Path):
    run = run_scanners(RECORDS, FIELDS, [NEVER_APPLIES, FINDS_NOTHING])
    assert run.scanner_status == {
        "never_applies": {"status": "not_applicable", "reason": "needs --files-root"},
        "finds_nothing": {"status": "ran"},
    }

    save_findings(run, tmp_path)
    summary = json.loads((tmp_path / "scan_summary.json").read_text())
    assert summary["scanner_status"] == run.scanner_status
    assert summary["by_scanner"] == {}
    assert "- `never_applies`: needs --files-root" in (tmp_path / "REPORT.md").read_text()


def test_terminal_report_lists_not_applicable_reason_verbatim():
    def _bracketed_reason(records: list[Record], fields: FieldMap) -> list[Finding]:
        raise ScannerNotApplicable("needs list[str] answers, not [/dim] markup")

    run = run_scanners(RECORDS, FIELDS, [ScannerDef(name="bracketed", fn=_bracketed_reason)])
    console = Console(record=True, width=200)
    print_report(run, console=console)
    assert (
        "Not applicable: bracketed (needs list[str] answers, not [/dim] markup)"
        in console.export_text()
    )


async def test_async_runner_records_status_for_sync_and_llm_scanners():
    async def _llm_never_applies(records: list[Record], fields: FieldMap) -> list[Finding]:
        raise ScannerNotApplicable("no context column")

    async def _llm_finds_one(records: list[Record], fields: FieldMap) -> list[Finding]:
        return [Finding("", "low", "format", "x", sample_index=0)]

    scanners = [
        NEVER_APPLIES,
        LLMScannerDef(name="llm_never_applies", fn=_llm_never_applies),
        LLMScannerDef(name="llm_finds_one", fn=_llm_finds_one),
    ]
    run = await run_scanners_async(RECORDS, FIELDS, scanners)
    assert run.scanner_status == {
        "never_applies": {"status": "not_applicable", "reason": "needs --files-root"},
        "llm_never_applies": {"status": "not_applicable", "reason": "no context column"},
        "llm_finds_one": {"status": "ran"},
    }
    assert [f.scanner for f in run.findings] == ["llm_finds_one"]
