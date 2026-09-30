from __future__ import annotations

import statistics
from typing import Any

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id
from inspect_dataset.scanners._answers import answer_texts, subfield_metadata
from inspect_dataset.scanners._groups import group_label, group_metadata, group_rows

# Fraction of the dataset that must share a property before deviations are flagged.
# E.g. if 80%+ of answers are lowercase, uppercase outliers are flagged.
_MAJORITY_THRESHOLD = 0.8
_LENGTH_STDEV_MULTIPLIER = 3.0  # flag if word count > mean + N * stdev


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    texts = answer_texts(records, fields, "inconsistent_format")
    findings: list[Finding] = []
    for group, rows in group_rows(records, fields, "inconsistent_format"):
        # (row index, element index, text): one per row, or one per element under a subfield
        units = [(i, j, text) for i in rows for j, text in enumerate(texts[i])]
        findings.extend(_scan_group(records, fields, units, group))
    return findings


def _scan_group(
    records: list[Record], fields: FieldMap, units: list[tuple[int, int, str]], group: Any
) -> list[Finding]:
    non_empty = [a for _, _, a in units if a]
    if len(non_empty) < 2:
        return []

    grouped = fields.group is not None
    majority = (
        f"the majority in group {group_label(fields, group)}" if grouped else "dataset majority"
    )
    in_group = f" in group {group_label(fields, group)}" if grouped else ""
    findings: list[Finding] = []

    # --- Capitalisation consistency ---
    lower_count = sum(1 for a in non_empty if a == a.lower())
    upper_first_count = sum(1 for a in non_empty if a and a[0].isupper())
    total = len(non_empty)

    mostly_lower = lower_count / total >= _MAJORITY_THRESHOLD
    mostly_upper_first = upper_first_count / total >= _MAJORITY_THRESHOLD

    for i, j, answer in units:
        if not answer:
            continue
        issues = []
        if mostly_lower and answer != answer.lower():
            issues.append(f"majority of answers are lowercase but this is not: {answer!r}")
        elif mostly_upper_first and not answer[0].isupper():
            issues.append(f"majority of answers start with uppercase but this does not: {answer!r}")

        if issues:
            findings.append(
                Finding(
                    scanner="inconsistent_format",
                    severity="low",
                    category="format",
                    explanation=f"Capitalisation differs from {majority}. " + "; ".join(issues),
                    sample_index=i,
                    sample_id=get_sample_id(records[i], fields, i),
                    metadata={
                        "answer": answer,
                        "issue": "capitalisation",
                        **subfield_metadata(fields, j),
                        **group_metadata(fields, group),
                    },
                )
            )

    # --- Trailing punctuation consistency ---
    has_punct = [a[-1] in ".!?" for a in non_empty if a]
    punct_count = sum(has_punct)
    mostly_punct = punct_count / total >= _MAJORITY_THRESHOLD
    mostly_no_punct = (total - punct_count) / total >= _MAJORITY_THRESHOLD

    for i, j, answer in units:
        if not answer:
            continue
        has_p = answer[-1] in ".!?" and not answer.endswith("etc.")
        issue = None
        if mostly_punct and not has_p:
            issue = f"majority of answers end with punctuation but this does not: {answer!r}"
        elif mostly_no_punct and has_p:
            issue = f"majority of answers have no trailing punctuation but this does: {answer!r}"

        if issue:
            findings.append(
                Finding(
                    scanner="inconsistent_format",
                    severity="low",
                    category="format",
                    explanation=f"Trailing punctuation differs from {majority}. {issue}",
                    sample_index=i,
                    sample_id=get_sample_id(records[i], fields, i),
                    metadata={
                        "answer": answer,
                        "issue": "trailing_punctuation",
                        **subfield_metadata(fields, j),
                        **group_metadata(fields, group),
                    },
                )
            )

    # --- Length outliers (word count) ---
    word_counts = [len(a.split()) for a in non_empty]
    mean_wc = statistics.mean(word_counts)
    if len(word_counts) >= 2:
        stdev_wc = statistics.stdev(word_counts)
        threshold = mean_wc + _LENGTH_STDEV_MULTIPLIER * stdev_wc
        for i, j, answer in units:
            if not answer:
                continue
            wc = len(answer.split())
            if wc > threshold:
                findings.append(
                    Finding(
                        scanner="inconsistent_format",
                        severity="medium",
                        category="format",
                        explanation=(
                            f"Answer is a length outlier{in_group}: {wc} words "
                            f"(mean={mean_wc:.1f}, stdev={stdev_wc:.1f}, "
                            f"threshold={threshold:.1f}). Answer: {answer!r}"
                        ),
                        sample_index=i,
                        sample_id=get_sample_id(records[i], fields, i),
                        metadata={
                            "answer": answer,
                            "word_count": wc,
                            "mean_word_count": round(mean_wc, 2),
                            "issue": "length_outlier",
                            **subfield_metadata(fields, j),
                            **group_metadata(fields, group),
                        },
                    )
                )

    return findings


inconsistent_format = ScannerDef(
    name="inconsistent_format",
    fn=_scan,
    requires="answer",
    description=(
        "Flag answers whose capitalisation, punctuation, or length deviate "
        "significantly from the dataset majority, or from each group's majority when "
        "grouping is on. Does not apply to list or struct answers "
        "unless --answer-subfield selects a scalar."
    ),
)
