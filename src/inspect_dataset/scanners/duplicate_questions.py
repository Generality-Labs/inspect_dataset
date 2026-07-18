from __future__ import annotations

import hashlib
from collections import defaultdict

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id


def _image_key(record: Record, image_field: str) -> str | None:
    """Return a stable key for the image in this record, or None if unavailable."""
    img = record.get(image_field)
    if img is None:
        return None
    if isinstance(img, dict):
        # HuggingFace Image(decode=False) → {"bytes": ..., "path": ...}
        raw = img.get("bytes")
        if raw:
            return hashlib.md5(raw).hexdigest()
        return img.get("path")
    if isinstance(img, (str, bytes)):
        return str(img)
    return None


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings = []

    if fields.image is not None:
        findings.extend(_scan_with_image(records, fields))
    else:
        findings.extend(_scan_without_image(records, fields))

    return findings


def _scan_with_image(records: list[Record], fields: FieldMap) -> list[Finding]:
    """When an image field is known, use (question, image) as the sample identity.

    Three cases:
    - Same question + same image  → HIGH: real duplicate, likely a copy error
    - Same question + diff image + same answer → MEDIUM: question is image-independent
      (the image contributes nothing — a model could answer without seeing it)
    - Same question + diff image + diff answer → LOW: standard VQA reuse, informational
    """
    assert fields.image is not None

    # Group by normalised question
    by_question: dict[str, list[tuple[int, Record]]] = defaultdict(list)
    for i, record in enumerate(records):
        q = str(record.get(fields.question, "") or "").strip().lower()
        by_question[q].append((i, record))

    findings = []
    for q_text, occurrences in by_question.items():
        if len(occurrences) <= 1:
            continue

        img_keys = [_image_key(r, fields.image) for _, r in occurrences]
        answers = [str(r.get(fields.answer, "") or "").strip().lower() for _, r in occurrences]
        indices = [idx for idx, _ in occurrences]

        # Group occurrences by image key to find exact (question, image) duplicates
        by_image: dict[str | None, list[tuple[int, Record]]] = defaultdict(list)
        for (idx, record), img_key in zip(occurrences, img_keys, strict=True):
            by_image[img_key].append((idx, record))

        # Emit HIGH finding for any (question, image) group that appears more than once
        for dups in by_image.values():
            if len(dups) <= 1:
                continue
            dup_indices = [idx for idx, _ in dups]
            for idx, record in dups:
                findings.append(
                    Finding(
                        scanner="duplicate_questions",
                        severity="high",
                        category="question_quality",
                        explanation=(
                            f"Question and image both appear {len(dups)} times "
                            f"(at indices {dup_indices}). This is a real duplicate sample."
                        ),
                        sample_index=idx,
                        sample_id=get_sample_id(record, fields, idx),
                        metadata={
                            "question": q_text,
                            "duplicate_indices": dup_indices,
                            "duplicate_count": len(dups),
                            "duplicate_type": "exact",
                        },
                    )
                )

        # Only emit question-reuse findings when images genuinely differ
        unique_img_keys = {k for k in img_keys if k is not None}
        if len(unique_img_keys) <= 1:
            continue  # all same image — already handled above as exact duplicates

        answers_agree = len(set(answers)) == 1
        if answers_agree:
            # Same question asked about different images, always gets the same answer —
            # the question is not actually image-dependent.
            severity: str = "medium"
            explanation = (
                f"Question appears {len(occurrences)} times across different images, "
                f"always with the same answer {answers[0]!r} (at indices {indices}). "
                f"The question appears image-independent — a model could answer it "
                f"without looking at the image."
            )
        else:
            # Same question, different images, different answers — standard VQA pattern.
            severity = "low"
            explanation = (
                f"Question text appears {len(occurrences)} times across different images "
                f"with different answers (at indices {indices}). "
                f"This is expected in VQA datasets but worth verifying."
            )

        for idx, record in occurrences:
            findings.append(
                Finding(
                    scanner="duplicate_questions",
                    severity=severity,  # type: ignore[arg-type]
                    category="question_quality",
                    explanation=explanation,
                    sample_index=idx,
                    sample_id=get_sample_id(record, fields, idx),
                    metadata={
                        "question": q_text,
                        "duplicate_indices": indices,
                        "duplicate_count": len(occurrences),
                        "duplicate_type": "question_reuse",
                        "answers_agree": answers_agree,
                    },
                )
            )

    return findings


def _scan_without_image(records: list[Record], fields: FieldMap) -> list[Finding]:
    """Without an image field, group by question only and classify by answer agreement."""
    seen: dict[str, list[tuple[int, Record]]] = defaultdict(list)
    for i, record in enumerate(records):
        q = str(record.get(fields.question, "") or "").strip().lower()
        seen[q].append((i, record))

    findings = []
    for q_text, occurrences in seen.items():
        if len(occurrences) <= 1:
            continue

        indices = [idx for idx, _ in occurrences]
        answers = [str(r.get(fields.answer, "") or "").strip().lower() for _, r in occurrences]
        answers_agree = len(set(answers)) == 1

        if answers_agree:
            severity: str = "high"
            explanation = (
                f"Question appears {len(occurrences)} times with the same answer "
                f"{answers[0]!r} (at indices {indices}). "
                "This is likely a duplicated sample."
            )
        else:
            severity = "low"
            explanation = (
                f"Question appears {len(occurrences)} times with different answers "
                f"(at indices {indices}). "
                "In multimodal datasets this is expected — use --image-field "
                "for precise classification."
            )

        for idx, record in occurrences:
            findings.append(
                Finding(
                    scanner="duplicate_questions",
                    severity=severity,  # type: ignore[arg-type]
                    category="question_quality",
                    explanation=explanation,
                    sample_index=idx,
                    sample_id=get_sample_id(record, fields, idx),
                    metadata={
                        "question": q_text,
                        "duplicate_indices": indices,
                        "duplicate_count": len(occurrences),
                        "answers_agree": answers_agree,
                    },
                )
            )

    return findings


duplicate_questions = ScannerDef(
    name="duplicate_questions",
    fn=_scan,
    description=(
        "Flag questions that appear more than once. "
        "With --image-field: exact (question+image) duplicates are HIGH; "
        "same question across different images with same answer is MEDIUM "
        "(image-independent question); different answers is LOW (standard VQA reuse). "
        "Without --image-field: same-answer duplicates are HIGH, different-answer are LOW."
    ),
)
