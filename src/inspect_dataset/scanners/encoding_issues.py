from __future__ import annotations

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id

# Control characters except for standard whitespace (\n \r \t are borderline —
# we flag \t and other non-printable controls but not \n/\r which can be
# legitimate in multi-line answers).
_CONTROL_CHARS = frozenset(range(0x20)) - {0x0A, 0x0D}  # exclude \n \r


def _find_bad_chars(text: str) -> list[str]:
    seen: list[str] = []
    for ch in text:
        cp = ord(ch)
        if (cp in _CONTROL_CHARS or cp == 0x7F) and repr(ch) not in seen:  # 0x7F = DEL
            seen.append(repr(ch))
    return seen


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings = []
    for i, record in enumerate(records):
        for field_role, field_name in (("question", fields.question), ("answer", fields.answer)):
            text = str(record.get(field_name, "") or "")
            bad = _find_bad_chars(text)
            if bad:
                findings.append(
                    Finding(
                        scanner="encoding_issues",
                        severity="low",
                        category="format",
                        explanation=(
                            f"The {field_role} contains non-printable character(s) "
                            f"{', '.join(bad)}. These are likely data entry errors "
                            f"and may cause silent failures in downstream processing. "
                            f"Value: {text!r}"
                        ),
                        sample_index=i,
                        sample_id=get_sample_id(record, fields, i),
                        metadata={
                            "field": field_role,
                            "bad_chars": bad,
                            "value": text,
                        },
                    )
                )
    return findings


encoding_issues = ScannerDef(
    name="encoding_issues",
    fn=_scan,
    description=(
        "Flag questions or answers containing non-printable or control characters "
        "(tabs, nulls, etc.) that are likely data entry errors."
    ),
)
