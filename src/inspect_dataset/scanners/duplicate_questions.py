from __future__ import annotations

from collections import defaultdict
from typing import Any

from inspect_dataset._types import FieldMap, Finding, Record, Severity
from inspect_dataset.scanner import ScannerDef, get_sample_id
from inspect_dataset.scanners._identity import (
    ImageKey,
    TextKey,
    answer_key,
    image_key,
    text_key,
)

Group = list[tuple[int, Record]]


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    by_text: dict[TextKey, Group] = defaultdict(list)
    for i, record in enumerate(records):
        by_text[text_key(record, fields)].append((i, record))
    groups = [(key, group) for key, group in by_text.items() if len(group) > 1]

    if fields.image is not None:
        return [f for key, group in groups for f in _image_group_findings(key, group, fields)]
    return [f for key, group in groups for f in _text_group_findings(key, group, fields)]


def _image_group_findings(key: TextKey, group: Group, fields: FieldMap) -> list[Finding]:
    """Findings for records that share their text and choices, when images are known.

    Three cases:
    - Same text + same images  → HIGH: real duplicate, likely a copy error
    - Same text + diff images + same answer → MEDIUM: question is image-independent
      (the image contributes nothing — a model could answer without seeing it)
    - Same text + diff images + diff answer → LOW: standard VQA reuse, informational
    """
    by_image: dict[ImageKey, Group] = defaultdict(list)
    for idx, record in group:
        by_image[image_key(record, fields)].append((idx, record))

    findings = []
    for img_key, dups in by_image.items():
        if len(dups) <= 1:
            continue
        agree = _answers_agree(dups, fields)
        shared = f"{_subject(key)} and image" if img_key else f"{_subject(key)}, with no image"
        findings.extend(
            _group_findings(
                dups,
                fields,
                severity="high",
                explanation=(
                    f"{len(dups)} samples share the {shared} (at indices {_indices(dups)}). "
                    "This is a real duplicate sample."
                ),
                metadata={
                    "question": key[0],
                    "duplicate_type": "exact",
                    "answers_agree": agree,
                },
            )
        )

    # Only emit question-reuse findings when images genuinely differ. No image (None)
    # counts as its own image, so a question asked with and without one is reuse.
    if len(by_image) <= 1:
        return findings

    agree = _answers_agree(group, fields)
    if agree:
        # Same question asked about different images, always gets the same answer —
        # the question is not actually image-dependent.
        severity: Severity = "medium"
        explanation = (
            f"{len(group)} samples share the {_subject(key)} across different images, "
            f"always with the same answer {_answer_text(group[0][1], fields)!r} "
            f"(at indices {_indices(group)}). The question appears image-independent: "
            "a model could answer it without looking at the image."
        )
    else:
        # Same question, different images, different answers — standard VQA pattern.
        severity = "low"
        explanation = (
            f"{len(group)} samples share the {_subject(key)} across different images, "
            f"with different answers (at indices {_indices(group)}). "
            "This is expected in VQA datasets but worth verifying."
        )
    findings.extend(
        _group_findings(
            group,
            fields,
            severity=severity,
            explanation=explanation,
            metadata={
                "question": key[0],
                "duplicate_type": "question_reuse",
                "answers_agree": agree,
            },
        )
    )
    return findings


def _text_group_findings(key: TextKey, group: Group, fields: FieldMap) -> list[Finding]:
    """Without an image field, classify records sharing their text by answer agreement."""
    agree = _answers_agree(group, fields)
    if agree:
        severity: Severity = "high"
        explanation = (
            f"{len(group)} samples share the {_subject(key)}, with the same answer "
            f"{_answer_text(group[0][1], fields)!r} (at indices {_indices(group)}). "
            "This is likely a duplicated sample."
        )
    else:
        severity = "low"
        explanation = (
            f"{len(group)} samples share the {_subject(key)}, with different answers "
            f"(at indices {_indices(group)}). "
            "In multimodal datasets this is expected — use --image-field "
            "for precise classification."
        )
    return _group_findings(
        group,
        fields,
        severity=severity,
        explanation=explanation,
        metadata={"question": key[0], "answers_agree": agree},
    )


def _group_findings(
    group: Group,
    fields: FieldMap,
    *,
    severity: Severity,
    explanation: str,
    metadata: dict[str, Any],
) -> list[Finding]:
    indices = [idx for idx, _ in group]
    return [
        Finding(
            scanner="duplicate_questions",
            severity=severity,
            category="question_quality",
            explanation=explanation,
            sample_index=idx,
            sample_id=get_sample_id(record, fields, idx),
            metadata={
                **metadata,
                "duplicate_indices": indices,
                "duplicate_count": len(group),
            },
        )
        for idx, record in group
    ]


def _answers_agree(group: Group, fields: FieldMap) -> bool:
    return len({answer_key(record, fields) for _, record in group}) == 1


def _answer_text(record: Record, fields: FieldMap) -> str:
    answers = sorted(answer_key(record, fields))
    return answers[0] if len(answers) == 1 else " | ".join(answers)


def _subject(key: TextKey) -> str:
    return "question" if key[1] is None else "question and choices"


def _indices(group: Group) -> list[int]:
    return [idx for idx, _ in group]


duplicate_questions = ScannerDef(
    name="duplicate_questions",
    fn=_scan,
    description=(
        "Flag samples that appear more than once. A sample is its question text, "
        "its choices when it has them, and its images by content. "
        "With an image field (--image-field, or the input images of a task): "
        "exact (question+image) duplicates are HIGH; "
        "same question across different images with same answer is MEDIUM "
        "(image-independent question); different answers is LOW (standard VQA reuse). "
        "Without --image-field: same-answer duplicates are HIGH, different-answer are LOW."
    ),
)
