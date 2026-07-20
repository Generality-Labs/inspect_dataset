from __future__ import annotations

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id
from inspect_dataset.scanners._artifacts import (
    body_offset,
    find_line,
    strip_markdown,
    tool_texts,
    word_tokens,
)

_MAX_LISTED = 12


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings: list[Finding] = []
    for i, record in enumerate(records):
        if record.get("ocr_resistant"):
            continue
        texts = tool_texts(record)
        if not texts:
            continue
        gold_raw = str(record.get(fields.answer, "") or "")
        gold = word_tokens(strip_markdown(gold_raw))
        if not gold:
            continue
        gold_covering = word_tokens(strip_markdown(gold_raw, strip_math=False))
        per_tool = [word_tokens(t) for t in texts.values()]
        union = set().union(*per_tool)
        intersection = set.intersection(*per_tool)
        sample_id = get_sample_id(record, fields, i)

        # Tokens no extraction tool saw anywhere on the page: the gold likely
        # contains a typo or content from elsewhere.
        unsupported = sorted(gold - union)
        if unsupported:
            listed = ", ".join(unsupported[:_MAX_LISTED])
            extra = len(unsupported) - _MAX_LISTED
            line = find_line(gold_raw, unsupported[0])
            findings.append(
                Finding(
                    scanner="text_layer_recall",
                    severity="high",
                    category="label_quality",
                    explanation=(
                        f"{len(unsupported)} gold word(s) appear in none of the "
                        f"{len(texts)} extraction tool outputs for this page: "
                        f"{listed}"
                        + (f" (+{extra} more)" if extra > 0 else "")
                        + ". Likely typos in the gold, or content that is not "
                        "on this page."
                    ),
                    sample_index=i,
                    sample_id=sample_id,
                    line=(line + body_offset(record)) if line is not None else None,
                    metadata={
                        "unsupported_words": unsupported[:50],
                        "tools": sorted(texts),
                    },
                )
            )

        # Omission check only makes sense when the gold covers the full page;
        # element-scoped gold legitimately omits the rest of the page.
        task_type = str(record.get("task_type", "") or "")
        if "page" not in task_type:
            continue
        omitted = sorted(intersection - gold_covering)
        if omitted:
            listed = ", ".join(omitted[:_MAX_LISTED])
            extra = len(omitted) - _MAX_LISTED
            findings.append(
                Finding(
                    scanner="text_layer_recall",
                    severity="medium",
                    category="label_quality",
                    explanation=(
                        f"{len(omitted)} word(s) found by every extraction tool "
                        f"are missing from the gold: {listed}"
                        + (f" (+{extra} more)" if extra > 0 else "")
                        + ". The gold may be incomplete for this page."
                    ),
                    sample_index=i,
                    sample_id=sample_id,
                    metadata={
                        "omitted_words": omitted[:50],
                        "tools": sorted(texts),
                    },
                )
            )
    return findings


text_layer_recall = ScannerDef(
    name="text_layer_recall",
    fn=_scan,
    description=(
        "Cross-check gold text against cached extraction tool outputs "
        "(requires --files-root): flag gold words no tool found on the page "
        "(typo/hallucination candidates) and, for full-page gold, words every "
        "tool found that the gold omits."
    ),
)
