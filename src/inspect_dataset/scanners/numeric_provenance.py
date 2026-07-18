from __future__ import annotations

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id
from inspect_dataset.scanners._artifacts import (
    body_offset,
    find_line,
    number_sources,
    number_tokens,
    strip_markdown,
    tool_texts,
)

_MAX_LISTED = 10


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings: list[Finding] = []
    for i, record in enumerate(records):
        if record.get("ocr_resistant"):
            continue
        texts = tool_texts(record)
        if not texts:
            continue
        gold_raw = str(record.get(fields.answer, "") or "")
        sources = number_sources(strip_markdown(gold_raw))
        gold_numbers = set(sources)
        if not gold_numbers:
            continue
        seen = set().union(*(number_tokens(t) for t in texts.values()))
        missing = sorted(gold_numbers - seen, key=lambda n: (len(n), n))
        if not missing:
            continue
        listed = ", ".join(missing[:_MAX_LISTED])
        extra = len(missing) - _MAX_LISTED
        line = find_line(gold_raw, sources[missing[0]])
        findings.append(
            Finding(
                scanner="numeric_provenance",
                severity="high",
                category="label_quality",
                explanation=(
                    f"{len(missing)} number(s) in the gold appear in none of the "
                    f"{len(texts)} extraction tool outputs for this page: {listed}"
                    + (f" (+{extra} more)" if extra > 0 else "")
                    + ". Numbers that no tool extracted are strong "
                    "transcription-error candidates."
                ),
                sample_index=i,
                sample_id=get_sample_id(record, fields, i),
                line=(line + body_offset(record)) if line is not None else None,
                metadata={"missing_numbers": missing[:50], "tools": sorted(texts)},
            )
        )
    return findings


numeric_provenance = ScannerDef(
    name="numeric_provenance",
    fn=_scan,
    description=(
        "Cross-check every number in the gold against cached extraction tool "
        "outputs (requires --files-root): a number no tool extracted from the "
        "page is a strong transcription-error candidate."
    ),
)
