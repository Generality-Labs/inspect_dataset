from __future__ import annotations

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id
from inspect_dataset.scanners._answers import answer_texts, subfield_metadata

DEFAULT_MAX_WORDS = 4


def _make_scanner(max_words: int = DEFAULT_MAX_WORDS) -> ScannerDef:
    def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
        findings = []
        texts = answer_texts(records, fields, "answer_length")
        for i, (record, elements) in enumerate(zip(records, texts, strict=True)):
            if not elements:
                continue
            counts = [len(e.split()) for e in elements]
            longest = max(range(len(elements)), key=counts.__getitem__)
            word_count, answer = counts[longest], elements[longest]
            if word_count > max_words:
                findings.append(
                    Finding(
                        scanner="answer_length",
                        severity="medium",
                        category="label_quality",
                        explanation=(
                            f"Answer has {word_count} words (threshold: {max_words}). "
                            f"Long answers are unlikely to be reproduced verbatim by "
                            f"exact-match scorers. Answer: {answer!r}"
                        ),
                        sample_index=i,
                        sample_id=get_sample_id(record, fields, i),
                        metadata={
                            "word_count": word_count,
                            "answer": answer,
                            **subfield_metadata(fields, longest),
                        },
                    )
                )
        return findings

    return ScannerDef(
        name="answer_length",
        fn=_scan,
        requires="answer",
        description=(
            f"Flag answers longer than {max_words} words. "
            "Long answers are a weak proxy for exact-match scoring. "
            "Does not apply to list or struct answers unless --answer-subfield selects a scalar."
        ),
    )


answer_length = _make_scanner()
