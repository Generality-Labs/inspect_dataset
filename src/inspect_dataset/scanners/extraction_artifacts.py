from __future__ import annotations

from inspect_dataset._types import FieldMap, Finding, Record, Severity
from inspect_dataset.scanner import ScannerDef, get_sample_id

# Characters that betray un-cleaned PDF/OCR extraction output.
_ARTIFACT_NAMES = {
    "ﬀ": "ligature ff (U+FB00)",
    "ﬁ": "ligature fi (U+FB01)",
    "ﬂ": "ligature fl (U+FB02)",
    "ﬃ": "ligature ffi (U+FB03)",
    "ﬄ": "ligature ffl (U+FB04)",
    "ﬅ": "ligature long-st (U+FB05)",
    "ﬆ": "ligature st (U+FB06)",
    "\u00ad": "soft hyphen (U+00AD)",
    "\u200b": "zero-width space (U+200B)",
    "\u200c": "zero-width non-joiner (U+200C)",
    "\u200d": "zero-width joiner (U+200D)",
    "\u2060": "word joiner (U+2060)",
    "\ufeff": "BOM / zero-width no-break space (U+FEFF)",
    "\u00a0": "non-breaking space (U+00A0)",
    "�": "replacement character (U+FFFD)",
}


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings: list[Finding] = []
    for i, record in enumerate(records):
        for field_role, field_name in (
            ("question", fields.question),
            ("answer", fields.answer),
        ):
            text = str(record.get(field_name, "") or "")
            found: dict[str, int] = {}
            first_line: int | None = None
            for line_no, line in enumerate(text.splitlines(), start=1):
                for ch in line:
                    if ch in _ARTIFACT_NAMES:
                        name = _ARTIFACT_NAMES[ch]
                        found[name] = found.get(name, 0) + 1
                        if first_line is None:
                            first_line = line_no
            if not found:
                continue
            offset_val = record.get("__md_body_offset__", 0)
            offset = offset_val if isinstance(offset_val, int) else 0
            severity: Severity = "medium" if "replacement character (U+FFFD)" in found else "low"
            summary = ", ".join(f"{name} x{n}" for name, n in sorted(found.items()))
            findings.append(
                Finding(
                    scanner="extraction_artifacts",
                    severity=severity,
                    category="format",
                    explanation=(
                        f"The {field_role} contains PDF-extraction artifact "
                        f"character(s): {summary}. These usually indicate the "
                        f"text was copied from an extractor without cleanup."
                    ),
                    sample_index=i,
                    sample_id=get_sample_id(record, fields, i),
                    line=(first_line + offset) if first_line is not None else None,
                    metadata={"field": field_role, "artifacts": found},
                )
            )
    return findings


extraction_artifacts = ScannerDef(
    name="extraction_artifacts",
    fn=_scan,
    description=(
        "Flag characters that betray un-cleaned PDF/OCR extraction: ligatures, "
        "soft hyphens, zero-width characters, non-breaking spaces, BOMs, and "
        "U+FFFD replacement characters."
    ),
)
