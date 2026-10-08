from __future__ import annotations

import unicodedata

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


# Zero-width joiners are part of how Bengali, Telugu, Persian and other scripts spell words,
# so one between two letters of such a script is orthography, not an extraction artifact.
_JOINERS = frozenset({"\u200c", "\u200d"})


def _script_letter(ch: str) -> bool:
    return unicodedata.category(ch)[0] in "LM" and "LATIN" not in unicodedata.name(ch, "LATIN")


def _joins_letters(line: str, pos: int) -> bool:
    return (
        0 < pos < len(line) - 1 and _script_letter(line[pos - 1]) and _script_letter(line[pos + 1])
    )


# Web text is full of non-breaking spaces, so in a published dataset one tells nothing on its
# own; it is counted beside another artifact. In local annotation files, extracted from PDFs,
# it is an extraction artifact like the others.
_NBSP = "non-breaking space (U+00A0)"
_PUBLISHED = frozenset({"hf", "inspect_task"})


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
                for pos, ch in enumerate(line):
                    if ch in _JOINERS and _joins_letters(line, pos):
                        continue
                    if ch in _ARTIFACT_NAMES:
                        name = _ARTIFACT_NAMES[ch]
                        found[name] = found.get(name, 0) + 1
                        if first_line is None:
                            first_line = line_no
            if not found or (set(found) == {_NBSP} and fields.source_type in _PUBLISHED):
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
        "U+FFFD replacement characters. In a HuggingFace or task dataset a non-breaking "
        "space is only reported beside another artifact."
    ),
)
