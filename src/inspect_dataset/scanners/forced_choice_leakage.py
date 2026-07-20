from __future__ import annotations

import re

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id

# Match " or " with optional surrounding whitespace, case-insensitive
_OR_PATTERN = re.compile(r"\bor\b", re.IGNORECASE)


def _extract_or_options(question: str) -> list[str]:
    """Return the words/phrases on each side of 'or' in a question.

    For "is this an MRI or a CT scan?", returns ["mri", "ct scan"].
    We strip articles and trailing punctuation to normalise for comparison.
    """
    articles = {"a", "an", "the"}

    parts = _OR_PATTERN.split(question)
    if len(parts) < 2:
        return []

    options = []
    for part in parts:
        # Take the last few tokens before 'or' and the first few after
        tokens = part.strip().rstrip("?.,!").split()
        # Remove leading articles
        while tokens and tokens[0].lower() in articles:
            tokens = tokens[1:]
        # Remove trailing articles
        while tokens and tokens[-1].lower() in articles:
            tokens = tokens[:-1]
        if tokens:
            options.append(" ".join(tokens).lower())

    return options


def _answer_matches_option(answer: str, options: list[str]) -> bool:
    """Return True if the answer is contained in or matches one of the options."""
    a = answer.lower().strip()
    return any(a == opt or opt.endswith(a) or a.endswith(opt) for opt in options)


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings = []
    for i, record in enumerate(records):
        question = str(record.get(fields.question, "") or "").strip()
        answer = str(record.get(fields.answer, "") or "").strip()

        if not _OR_PATTERN.search(question):
            continue

        options = _extract_or_options(question)
        if len(options) < 2:
            continue

        if _answer_matches_option(answer, options):
            findings.append(
                Finding(
                    scanner="forced_choice_leakage",
                    severity="medium",
                    category="leakage",
                    explanation=(
                        f"Question explicitly offers the answer as one of its options "
                        f"('...or...'). A model can select the correct answer by "
                        f"pattern-matching the question without understanding the content. "
                        f"Question: {question!r}  Answer: {answer!r}"
                    ),
                    sample_index=i,
                    sample_id=get_sample_id(record, fields, i),
                    metadata={
                        "question": question,
                        "answer": answer,
                        "options": options,
                    },
                )
            )
    return findings


forced_choice_leakage = ScannerDef(
    name="forced_choice_leakage",
    fn=_scan,
    description=(
        "Flag questions that offer explicit options via 'or' where the answer "
        "is one of those options (e.g. 'is this an MRI or CT scan?' → 'mri'). "
        "A model can exploit the phrasing without understanding the content."
    ),
)
