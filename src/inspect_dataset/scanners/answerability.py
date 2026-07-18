"""LLM scanner: flag questions that cannot be answered from the provided context.

In many evaluation datasets, questions are paired with a context passage
(or an image). This scanner checks whether the question is actually
answerable given only the information in the provided context. Unanswerable
questions with expected answers are a dataset quality issue — they test
memorisation or hallucination rather than comprehension.
"""

from __future__ import annotations

from inspect_dataset._llm import LLMJudgment, get_model, judge_batch
from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import LLMScannerDef, get_sample_id

_PROMPT_TEMPLATE_WITH_CONTEXT = """\
You are auditing a sample from an AI evaluation dataset.

Context: {context}
Question: {question}
Expected answer: {answer}

Is this question UNANSWERABLE from the provided context alone? A question is
unanswerable if:
- The context does not contain enough information to determine the answer
- The answer requires knowledge not present in the context
- The context is irrelevant to the question

Do NOT flag a question as unanswerable just because it is difficult. Only flag
it if the provided context genuinely lacks the information needed.

Answer YES if the question is unanswerable from context, NO if it can be
answered. Start your response with YES or NO, then explain briefly."""

_PROMPT_TEMPLATE_NO_CONTEXT = """\
You are auditing a sample from an AI evaluation dataset.

Question: {question}
Expected answer: {answer}

This question has no accompanying context passage. Is this question
UNANSWERABLE as a standalone question? A question is unanswerable if:
- It refers to a specific image, passage, or document not provided
- It uses demonstratives like "this", "the following" without a referent
- It requires information that is not self-contained in the question

Do NOT flag general knowledge questions as unanswerable — those are fine
without context.

Answer YES if the question appears unanswerable without missing context,
NO if it is self-contained. Start your response with YES or NO, then explain
briefly."""

# Common field names for context columns
_CONTEXT_CANDIDATES = [
    "context",
    "passage",
    "paragraph",
    "text",
    "document",
    "input_text",
]


def _find_context_field(record: Record, fields: FieldMap) -> str | None:
    """Try to find a context field in the record."""
    for candidate in _CONTEXT_CANDIDATES:
        if candidate in record and candidate != fields.question and candidate != fields.answer:
            val = record[candidate]
            if val and str(val).strip():
                return candidate
    return None


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

            context_field = _find_context_field(record, fields)
            if context_field:
                context = str(record[context_field]).strip()
                prompts.append(
                    _PROMPT_TEMPLATE_WITH_CONTEXT.format(
                        context=context, question=question, answer=answer
                    )
                )
            else:
                prompts.append(_PROMPT_TEMPLATE_NO_CONTEXT.format(question=question, answer=answer))
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
                context_field = _find_context_field(record, fields)
                findings.append(
                    Finding(
                        scanner="answerability",
                        severity="medium",
                        category="question_quality",
                        explanation=(
                            "LLM flagged this question as "
                            "unanswerable "
                            + ("from the provided context" if context_field else "without context")
                            + f". Question: {question!r}  "
                            f"Answer: {answer!r}  "
                            f"Reasoning: {judgment.reasoning}"
                        ),
                        sample_index=idx,
                        sample_id=get_sample_id(record, fields, idx),
                        metadata={
                            "question": question,
                            "answer": answer,
                            "has_context": context_field is not None,
                            "context_field": context_field,
                            "llm_reasoning": judgment.reasoning,
                            "llm_raw_response": judgment.raw_response,
                        },
                    )
                )
        return findings

    return LLMScannerDef(
        name="answerability",
        fn=_scan,
        description=(
            "LLM-based scanner that flags questions which cannot be answered "
            "from the provided context alone. Unanswerable questions with "
            "expected answers test memorisation rather than comprehension."
        ),
    )
