from __future__ import annotations

from typing import Any

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef
from inspect_dataset.scanners._groups import (
    MIN_GROUP_SIZE,
    group_label,
    group_metadata,
    population_groups,
)

_BINARY_ANSWERS = frozenset({"yes", "no"})
_FLAG_THRESHOLD = 0.5  # flag when more than half of answers are yes/no


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    answers = [str(record.get(fields.answer, "") or "").strip().lower() for record in records]
    findings: list[Finding] = []
    for group, non_empty in population_groups(records, fields, "binary_question_ratio", answers):
        finding = _check(non_empty, fields, group)
        if finding is not None:
            findings.append(finding)
    return findings


def _check(non_empty: list[str], fields: FieldMap, group: Any) -> Finding | None:
    binary_count = sum(1 for a in non_empty if a in _BINARY_ANSWERS)
    total = len(non_empty)
    fraction = binary_count / total

    if fraction <= _FLAG_THRESHOLD:
        return None

    yes_count = sum(1 for a in non_empty if a == "yes")
    no_count = sum(1 for a in non_empty if a == "no")
    majority_answer = "yes" if yes_count >= no_count else "no"
    majority_count = max(yes_count, no_count)
    naive_score = majority_count / total

    prefix = "" if fields.group is None else f"In group {group_label(fields, group)}, "
    return Finding(
        scanner="binary_question_ratio",
        severity="low",
        category="distribution",
        explanation=(
            f"{prefix}{binary_count}/{total} samples ({fraction:.0%}) have binary yes/no "
            f"answers. A model that always predicts '{majority_answer}' would score "
            f"{naive_score:.0%} without understanding any questions. "
            f"Consider whether the yes/no balance is appropriate for your benchmark."
        ),
        sample_index=-1,
        sample_id=None,
        metadata={
            "binary_count": binary_count,
            "total": total,
            "fraction": round(fraction, 4),
            "yes_count": yes_count,
            "no_count": no_count,
            "naive_majority_score": round(naive_score, 4),
            **group_metadata(fields, group),
        },
    )


binary_question_ratio = ScannerDef(
    name="binary_question_ratio",
    fn=_scan,
    requires="answer",
    description=(
        f"Flag datasets where more than {_FLAG_THRESHOLD:.0%} of answers are yes/no. "
        "High binary ratios mean a majority-class baseline can score well without "
        "understanding the questions. With grouping, each group of at least "
        f"{MIN_GROUP_SIZE} samples is checked on its own."
    ),
)
