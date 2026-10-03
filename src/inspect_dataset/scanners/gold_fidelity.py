"""Vision LLM scanner: flag gold markdown that misrepresents the page image.

The gold markdown in a page-roundtrip / element-reproduction dataset is meant to
faithfully reproduce what is on the rendered page. This scanner shows the model
the page image alongside the gold markdown and asks whether the markdown
contains a material fidelity error — a wrong number, a dropped or invented row,
a garbled heading — relative to what the page actually shows.

It reads the page image from the extraction cache via ``--files-root`` (records
without a page image are skipped), so it only runs when artifacts are attached.
"""

from __future__ import annotations

from inspect_dataset._llm import LLMJudgment, get_model, judge_batch_vision
from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import LLMScannerDef, get_sample_id
from inspect_dataset.scanners._artifacts import page_image

_PROMPT_TEMPLATE = """\
You are auditing a sample from a document-understanding dataset. The image is a
rendered page (or page element). The text below is the gold markdown that is
supposed to reproduce the content of that image faithfully.

Gold markdown:
---
{answer}
---

Does the gold markdown contain a MATERIAL fidelity error relative to the image?
Flag it only for substantive discrepancies, such as:
- A number, date, or total that differs from what the image shows
- A table row, column, or cell that is missing, invented, or misplaced
- Text that is garbled, mis-transcribed, or attributed to the wrong heading
- Content clearly present on the page that the markdown omits entirely

Do NOT flag benign formatting differences: reasonable markdown structure,
whitespace, cell alignment, or ordering that preserves meaning.

Answer YES if there is a material fidelity error, NO if the markdown faithfully
reproduces the image. Start your response with YES or NO, then explain briefly."""


def _make_scanner(model_name: str, concurrency: int = 20) -> LLMScannerDef:
    async def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
        model = get_model(model_name)

        prompts: list[str] = []
        images: list[bytes | None] = []
        indices: list[int] = []
        for i, record in enumerate(records):
            answer = str(record.get(fields.answer, "") or "").strip()
            if not answer:
                continue
            image = page_image(record)
            if image is None:
                continue
            prompts.append(_PROMPT_TEMPLATE.format(answer=answer))
            images.append(image)
            indices.append(i)

        if not prompts:
            return []

        judgments: list[LLMJudgment] = await judge_batch_vision(
            model, prompts, images, concurrency=concurrency
        )

        findings: list[Finding] = []
        for idx, judgment in zip(indices, judgments, strict=True):
            if judgment.flagged:
                record = records[idx]
                findings.append(
                    Finding(
                        scanner="gold_fidelity",
                        severity="high",
                        category="label_quality",
                        explanation=(
                            "Vision model flagged the gold markdown as unfaithful to the "
                            f"page image. Reasoning: {judgment.reasoning}"
                        ),
                        sample_index=idx,
                        sample_id=get_sample_id(record, fields, idx),
                        metadata={
                            "llm_reasoning": judgment.reasoning,
                            "llm_raw_response": judgment.raw_response,
                        },
                    )
                )
        return findings

    return LLMScannerDef(
        name="gold_fidelity",
        fn=_scan,
        description=(
            "Vision LLM scanner that shows the model the page image and flags gold "
            "markdown that materially misrepresents it (wrong numbers, dropped or "
            "invented rows, garbled text). Requires --files-root for the page image."
        ),
    )
