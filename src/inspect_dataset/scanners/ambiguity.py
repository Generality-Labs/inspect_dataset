"""LLM scanner: flag questions that are ambiguous or underspecified.

An ambiguous question can be reasonably interpreted in multiple ways,
leading to unreliable evaluation — different annotators (or models) might
arrive at different correct answers.
"""

from __future__ import annotations

from inspect_dataset._llm import LLMJudgment, get_model, judge_batch
from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import LLMScannerDef, get_sample_id

_PROMPT_TEMPLATE = """\
You are auditing a question from an AI evaluation dataset.

Question: {question}
Expected answer: {answer}

Is this question AMBIGUOUS? A question is ambiguous if:
- It can be reasonably interpreted in multiple ways
- It is missing critical context needed to arrive at a single correct answer
- The expected answer depends on unstated assumptions
- It is so vague that multiple different answers would be defensible

Answer YES if the question is ambiguous, NO if it is clear and unambiguous.
Start your response with YES or NO, then explain briefly."""


def _make_scanner(model_name: str, concurrency: int = 20) -> LLMScannerDef:
    async def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
        model = get_model(model_name)

        prompts = []
        indices = []
        for i, record in enumerate(records):
            question = str(record.get(fields.question, "") or "").strip()
            answer = str(record.get(fields.answer, "") or "").strip()
            if not question:
                continue
            prompts.append(_PROMPT_TEMPLATE.format(question=question, answer=answer))
            indices.append(i)

        if not prompts:
            return []

        judgments: list[LLMJudgment] = await judge_batch(model, prompts, concurrency=concurrency)

        findings = []
        for idx, judgment in zip(indices, judgments, strict=True):
            if judgment.flagged:
                record = records[idx]
                question = str(record.get(fields.question, "") or "").strip()
                answer = str(record.get(fields.answer, "") or "").strip()
                findings.append(
                    Finding(
                        scanner="ambiguity",
                        severity="medium",
                        category="question_quality",
                        explanation=(
                            f"LLM flagged this question as ambiguous. "
                            f"Question: {question!r}  Answer: {answer!r}  "
                            f"Reasoning: {judgment.reasoning}"
                        ),
                        sample_index=idx,
                        sample_id=get_sample_id(record, fields, idx),
                        metadata={
                            "question": question,
                            "answer": answer,
                            "llm_reasoning": judgment.reasoning,
                            "llm_raw_response": judgment.raw_response,
                        },
                    )
                )
        return findings

    return LLMScannerDef(
        name="ambiguity",
        fn=_scan,
        description=(
            "LLM-based scanner that flags questions which are ambiguous or "
            "underspecified — questions that can be reasonably interpreted in "
            "multiple ways, leading to unreliable evaluation."
        ),
    )
