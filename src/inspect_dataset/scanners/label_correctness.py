"""LLM scanner: flag samples where the ground-truth answer appears incorrect.

A label correctness check asks the LLM whether the expected answer is
actually correct for the given question. Incorrect labels are one of the
most damaging dataset quality issues — they directly corrupt evaluation
metrics.
"""

from __future__ import annotations

from inspect_dataset._llm import LLMJudgment, get_model, judge_batch
from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import LLMScannerDef, get_sample_id

_PROMPT_TEMPLATE = """\
You are auditing a sample from an AI evaluation dataset.

Question: {question}
Expected answer: {answer}

Is the expected answer INCORRECT? An answer is incorrect if:
- It is factually wrong given the question
- It is a plausible-sounding but wrong answer
- It contradicts well-established knowledge
- It answers a different question than the one asked

Do NOT flag an answer as incorrect just because it is short, informal, or
could be phrased better. Only flag it if the answer is genuinely wrong.

Answer YES if the expected answer is incorrect, NO if it appears correct.
Start your response with YES or NO, then explain briefly."""


def _make_scanner(model_name: str, concurrency: int = 20) -> LLMScannerDef:
    async def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
        model = get_model(model_name)

        prompts = []
        indices = []
        for i, record in enumerate(records):
            question = str(record.get(fields.question, "") or "").strip()
            answer = str(record.get(fields.answer, "") or "").strip()
            if not question or not answer:
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
                        scanner="label_correctness",
                        severity="high",
                        category="label_quality",
                        explanation=(
                            f"LLM flagged this answer as potentially incorrect. "
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
        name="label_correctness",
        fn=_scan,
        description=(
            "LLM-based scanner that flags samples where the ground-truth "
            "answer appears to be incorrect — the most damaging dataset "
            "quality issue for evaluation metrics."
        ),
    )
