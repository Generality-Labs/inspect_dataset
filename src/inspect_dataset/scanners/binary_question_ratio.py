from __future__ import annotations

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef

_BINARY_ANSWERS = frozenset({"yes", "no"})
_FLAG_THRESHOLD = 0.5  # flag when more than half of answers are yes/no


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    answers = [str(record.get(fields.answer, "") or "").strip().lower() for record in records]
    non_empty = [a for a in answers if a]
    if not non_empty:
        return []

    binary_count = sum(1 for a in non_empty if a in _BINARY_ANSWERS)
    total = len(non_empty)
    fraction = binary_count / total

    if fraction <= _FLAG_THRESHOLD:
        return []

    yes_count = sum(1 for a in non_empty if a == "yes")
    no_count = sum(1 for a in non_empty if a == "no")
    majority_answer = "yes" if yes_count >= no_count else "no"
    majority_count = max(yes_count, no_count)
    naive_score = majority_count / total

    return [
        Finding(
            scanner="binary_question_ratio",
            severity="low",
            category="distribution",
            explanation=(
                f"{binary_count}/{total} samples ({fraction:.0%}) have binary yes/no answers. "
                f"A model that always predicts '{majority_answer}' would score "
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
            },
        )
    ]


binary_question_ratio = ScannerDef(
    name="binary_question_ratio",
    fn=_scan,
    requires="answer",
    description=(
        f"Flag datasets where more than {_FLAG_THRESHOLD:.0%} of answers are yes/no. "
        "High binary ratios mean a majority-class baseline can score well without "
        "understanding the questions."
    ),
)
