from __future__ import annotations

from collections import Counter

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef

_IMBALANCE_THRESHOLD = 0.85  # flag if one answer accounts for ≥85% of all answers


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    answers = [str(record.get(fields.answer, "") or "").strip().lower() for record in records]
    non_empty = [a for a in answers if a]
    if not non_empty:
        return []

    counts = Counter(non_empty)
    total = len(non_empty)
    most_common_answer, most_common_count = counts.most_common(1)[0]
    fraction = most_common_count / total

    if fraction < _IMBALANCE_THRESHOLD:
        return []

    # One finding at the dataset level (index -1, no sample_id)
    return [
        Finding(
            scanner="answer_distribution",
            severity="high",
            category="distribution",
            explanation=(
                f"Dataset is heavily imbalanced: {most_common_count}/{total} samples "
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
            },
        )
    ]


answer_distribution = ScannerDef(
    name="answer_distribution",
    fn=_scan,
    description=(
        f"Flag datasets where a single answer accounts for ≥{_IMBALANCE_THRESHOLD:.0%} "
        "of all samples (class imbalance)."
    ),
)
