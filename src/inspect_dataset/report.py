from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from inspect_dataset._types import FieldMap, Record, ScanRun
from inspect_dataset._version import package_version

_SEVERITY_COLOUR = {"high": "red", "medium": "yellow", "low": "cyan"}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _not_applicable(run: ScanRun) -> list[tuple[str, str]]:
    return sorted(
        (name, status.get("reason", ""))
        for name, status in run.scanner_status.items()
        if status.get("status") == "not_applicable"
    )


def _source_suffix(run: ScanRun) -> str:
    return f" ({run.group_by_source})" if run.group_by_source else ""


def print_report(run: ScanRun, console: Console | None = None) -> None:
    """Print a rich summary of scan results to the terminal."""
    if console is None:
        console = Console()

    console.print()
    console.rule(f"[bold]inspect-dataset {package_version()} scan report[/bold]")
    console.print(
        f"  Dataset: [bold]{run.dataset_name}[/bold]"
        + (f"  split={run.split}" if run.split else "")
    )
    if run.scorers:
        console.print(f"  Scorers: {', '.join(run.scorers)}")
    console.print(f"  Samples: {run.total_samples:,}")
    if run.group_by is not None:
        console.print(f"  Grouped by: {run.group_by}{_source_suffix(run)}")
    console.print(f"  Total findings: {len(run.findings):,}")
    for name, reason in _not_applicable(run):
        console.print(f"  [dim]Not applicable: {escape(name)} ({escape(reason)})[/dim]")
    console.print()

    if not run.findings:
        console.print("[green]No issues found.[/green]")
        return

    # Summary table: one row per scanner
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Scanner")
    table.add_column("Findings", justify="right")
    table.add_column("High", justify="right", style="red")
    table.add_column("Medium", justify="right", style="yellow")
    table.add_column("Low", justify="right", style="cyan")
    table.add_column("Description")

    by_scanner = run.by_scanner()
    for scanner_name, findings in sorted(by_scanner.items()):
        high = sum(1 for f in findings if f.severity == "high")
        med = sum(1 for f in findings if f.severity == "medium")
        low = sum(1 for f in findings if f.severity == "low")
        table.add_row(
            scanner_name,
            str(len(findings)),
            str(high) if high else "",
            str(med) if med else "",
            str(low) if low else "",
            "",
        )

    console.print(table)

    # Detail: top findings per scanner (up to 5 each)
    for scanner_name, findings in sorted(by_scanner.items()):
        findings_sorted = sorted(findings, key=lambda f: _SEVERITY_ORDER[f.severity])
        console.rule(
            f"[bold]{scanner_name}[/bold] "
            f"({len(findings)} finding{'s' if len(findings) != 1 else ''})"
        )
        for f in findings_sorted[:5]:
            colour = _SEVERITY_COLOUR[f.severity]
            id_str = f"id={f.sample_id}" if f.sample_id is not None else f"index={f.sample_index}"
            console.print(
                f"  [{colour}][{f.severity.upper()}][/{colour}] [{id_str}] {f.explanation}"
            )
        if len(findings) > 5:
            console.print(f"  [dim]... and {len(findings) - 5} more (see output files)[/dim]")
        console.print()


def save_findings(
    run: ScanRun,
    output_dir: Path,
    records: list[Record] | None = None,
    fields: FieldMap | None = None,
    files_root: str | None = None,
) -> None:
    """Write per-scanner JSON files, a summary, and optionally samples to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    by_scanner = run.by_scanner()
    for scanner_name, findings in by_scanner.items():
        out = output_dir / f"{scanner_name}.json"
        out.write_text(json.dumps([f.to_dict() for f in findings], indent=2, default=str))

    summary = {
        "version": package_version(),
        "dataset_name": run.dataset_name,
        "split": run.split,
        "source_type": run.source_type,
        "revision": run.revision,
        "config": run.config,
        "group_by": run.group_by,
        "group_by_source": run.group_by_source,
        "task": run.task,
        "scorers": run.scorers,
        "split_defaulted": run.split_defaulted,
        "config_defaulted": run.config_defaulted,
        "files_root": files_root,
        "total_samples": run.total_samples,
        "total_findings": len(run.findings),
        "by_scanner": {
            name: {
                "total": len(findings),
                "high": sum(1 for f in findings if f.severity == "high"),
                "medium": sum(1 for f in findings if f.severity == "medium"),
                "low": sum(1 for f in findings if f.severity == "low"),
            }
            for name, findings in by_scanner.items()
        },
        "by_severity": {sev: len(findings) for sev, findings in run.by_severity().items()},
        "scanner_status": run.scanner_status,
    }
    (output_dir / "scan_summary.json").write_text(json.dumps(summary, indent=2))

    # Write samples.json if records and fields are provided
    if records is not None and fields is not None:
        samples = []
        for i, rec in enumerate(records):
            sample: dict[str, Any] = {
                "index": i,
                "question": _as_text(rec.get(fields.question)),
                "answer": _as_text(rec.get(fields.answer)),
            }
            if fields.id and fields.id in rec:
                sample["id"] = rec[fields.id]
            samples.append(sample)
        (output_dir / "samples.json").write_text(json.dumps(samples, indent=2, default=str))

    _write_markdown_report(run, output_dir / "REPORT.md")


def _as_text(value: Any) -> str:
    """A samples.json field as a string, which the viewer expects: lists and structs as JSON."""
    if value is None:
        return ""
    if isinstance(value, Mapping | list | tuple):
        try:
            return json.dumps(value, indent=2, ensure_ascii=False, default=_json_default)
        except (TypeError, ValueError):
            # Non-string dict keys or a circular value: a repr beats losing the scan output
            return str(value)
    return str(value)


def _json_default(value: Any) -> str:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return str(value)


def _write_markdown_report(run: ScanRun, path: Path) -> None:
    lines = [
        "# inspect-dataset Report",
        "",
        f"**inspect-dataset version:** {package_version()}",
        f"**Dataset:** {run.dataset_name}" + (f" (split: `{run.split}`)" if run.split else ""),
    ]
    if run.scorers:
        lines.append("**Scorers:** " + ", ".join(f"`{s}`" for s in run.scorers))
    lines += [
        f"**Samples scanned:** {run.total_samples:,}",
    ]
    if run.group_by is not None:
        lines.append(f"**Grouped by:** `{run.group_by}`{_source_suffix(run)}")
    lines += [
        f"**Total findings:** {len(run.findings):,}",
        "",
        "## Summary",
        "",
        "| Scanner | Findings | High | Medium | Low |",
        "|---|---|---|---|---|",
    ]

    by_scanner = run.by_scanner()
    for name, findings in sorted(by_scanner.items()):
        high = sum(1 for f in findings if f.severity == "high")
        med = sum(1 for f in findings if f.severity == "medium")
        low = sum(1 for f in findings if f.severity == "low")
        lines.append(f"| `{name}` | {len(findings)} | {high} | {med} | {low} |")

    not_applicable = _not_applicable(run)
    if not_applicable:
        lines += ["", "## Not applicable", ""]
        lines += [f"- `{name}`: {reason}" for name, reason in not_applicable]

    lines += ["", "## Findings", ""]

    for scanner_name, findings in sorted(by_scanner.items()):
        lines.append(f"### {scanner_name}")
        lines.append("")
        for f in sorted(findings, key=lambda f: _SEVERITY_ORDER[f.severity]):
            id_str = f"id={f.sample_id}" if f.sample_id is not None else f"index={f.sample_index}"
            lines.append(f"- **[{f.severity.upper()}]** [{id_str}] {f.explanation}")
        lines.append("")

    path.write_text("\n".join(lines))
