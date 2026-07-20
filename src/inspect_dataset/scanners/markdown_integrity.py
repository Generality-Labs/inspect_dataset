from __future__ import annotations

import re

from inspect_dataset._types import FieldMap, Finding, Record, Severity
from inspect_dataset.scanner import ScannerDef, get_sample_id

_DELIMITER_ROW = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
_HEADING = re.compile(r"^(#{1,6})\s")
_IMAGE_LINK = re.compile(r"!\[[^\]]*\]\(([^)]*)\)")


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _check_table(
    block: list[tuple[int, str]],
    make: _FindingFactory,
) -> list[Finding]:
    findings: list[Finding] = []
    header_line, header = block[0]
    n_cols = len(_cells(header))

    if len(block) < 2 or not (_DELIMITER_ROW.match(block[1][1]) and "-" in block[1][1]):
        findings.append(
            make(
                "medium",
                f"Table starting at line {header_line} has no delimiter row "
                "(| --- | ... |) after the header; it will not render as a table.",
                header_line,
                {"table_line": header_line},
            )
        )
        body = block[1:]
    else:
        body = block[2:]

    for line_no, row in body:
        cells = _cells(row)
        if len(cells) != n_cols:
            findings.append(
                make(
                    "medium",
                    f"Table row at line {line_no} has {len(cells)} cell(s) but "
                    f"the header at line {header_line} has {n_cols}. "
                    f"Row: {row.strip()!r}",
                    line_no,
                    {
                        "expected_cols": n_cols,
                        "actual_cols": len(cells),
                        "row": row.strip(),
                    },
                )
            )
        elif all(c == "" for c in cells):
            findings.append(
                make(
                    "low",
                    f"Table row at line {line_no} is entirely empty.",
                    line_no,
                    {"row": row.strip()},
                )
            )
    return findings


class _FindingFactory:
    def __init__(self, index: int, sample_id: str | int | None, offset: int) -> None:
        self.index = index
        self.sample_id = sample_id
        self.offset = offset

    def __call__(
        self,
        severity: Severity,
        explanation: str,
        line: int,
        metadata: dict[str, object],
    ) -> Finding:
        return Finding(
            scanner="markdown_integrity",
            severity=severity,
            category="format",
            explanation=explanation,
            sample_index=self.index,
            sample_id=self.sample_id,
            line=line + self.offset,
            metadata=dict(metadata),
        )


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings: list[Finding] = []
    for i, record in enumerate(records):
        text = str(record.get(fields.answer, "") or "")
        if "|" not in text and "#" not in text and "![" not in text:
            continue
        offset_val = record.get("__md_body_offset__", 0)
        offset = offset_val if isinstance(offset_val, int) else 0
        make = _FindingFactory(i, get_sample_id(record, fields, i), offset)

        lines = text.splitlines()
        table_block: list[tuple[int, str]] = []
        prev_heading_level = 0
        for line_no, line in enumerate(lines, start=1):
            if _is_table_row(line):
                table_block.append((line_no, line))
                continue
            if table_block:
                findings.extend(_check_table(table_block, make))
                table_block = []

            heading = _HEADING.match(line)
            if heading:
                level = len(heading.group(1))
                if prev_heading_level and level > prev_heading_level + 1:
                    findings.append(
                        make(
                            "low",
                            f"Heading at line {line_no} jumps from level "
                            f"{prev_heading_level} to {level}: {line.strip()!r}",
                            line_no,
                            {"from_level": prev_heading_level, "to_level": level},
                        )
                    )
                prev_heading_level = level

            for match in _IMAGE_LINK.finditer(line):
                if not match.group(1).strip():
                    findings.append(
                        make(
                            "medium",
                            f"Image link at line {line_no} has an empty target: {match.group(0)!r}",
                            line_no,
                            {"link": match.group(0)},
                        )
                    )
        if table_block:
            findings.extend(_check_table(table_block, make))
    return findings


markdown_integrity = ScannerDef(
    name="markdown_integrity",
    fn=_scan,
    description=(
        "Flag structural problems in Markdown answers: table rows whose column "
        "count differs from the header, missing delimiter rows, empty table "
        "rows, heading-level jumps, and image links with empty targets."
    ),
)
