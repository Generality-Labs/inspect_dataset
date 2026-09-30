from __future__ import annotations

from collections import Counter
from typing import Any

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef
from inspect_dataset.scanners._groups import (
    MIN_GROUP_SIZE,
    group_label,
    group_metadata,
    population_groups,
)

_IMBALANCE_THRESHOLD = 0.85  # flag if one answer accounts for ≥85% of all answers


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    answers = [str(record.get(fields.answer, "") or "").strip().lower() for record in records]
    findings: list[Finding] = []
    for group, non_empty in population_groups(records, fields, "answer_distribution", answers):
        finding = _check(non_empty, fields, group)
        if finding is not None:
            findings.append(finding)
    return findings


def _check(non_empty: list[str], fields: FieldMap, group: Any) -> Finding | None:
    counts = Counter(non_empty)
    total = len(non_empty)
    most_common_answer, most_common_count = counts.most_common(1)[0]
    fraction = most_common_count / total

    if fraction < _IMBALANCE_THRESHOLD:
        return None

    subject = "Dataset" if fields.group is None else f"Group {group_label(fields, group)}"
    # One finding at the dataset or group level (index -1, no sample_id)
    return Finding(
        scanner="answer_distribution",
        severity="high",
        category="distribution",
        explanation=(
            f"{subject} is heavily imbalanced: {most_common_count}/{total} samples "
            f"({fraction:.0%}) have the answer {most_common_answer!r}. "
            f"A model that always predicts {most_common_answer!r} would score "
            f"{fraction:.0%} without understanding the questions."
        ),
        sample_index=-1,
        sample_id=None,
        metadata={
            "most_common_answer": most_common_answer,
            "most_common_count": most_common_count,
            "total": total,
            "fraction": round(fraction, 4),
            "top_10": counts.most_common(10),
            **group_metadata(fields, group),
        },
    )


answer_distribution = ScannerDef(
    name="answer_distribution",
    fn=_scan,
    requires="answer",
    description=(
        f"Flag datasets where a single answer accounts for ≥{_IMBALANCE_THRESHOLD:.0%} "
        "of all samples (class imbalance). With grouping, each group of at least "
        f"{MIN_GROUP_SIZE} samples is checked on its own."
    ),
)
