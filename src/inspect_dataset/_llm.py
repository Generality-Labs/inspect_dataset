"""LLM helper utilities for async scanners.

Uses inspect_ai's model API to call LLMs. Provides:
- Model resolution from a model name string
- Concurrent batch evaluation with semaphore-based rate limiting
- Structured yes/no judgment extraction from LLM responses
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Default concurrency limit for LLM calls
DEFAULT_CONCURRENCY = 20


@dataclass
class LLMJudgment:
    """Result of an LLM judgment on a single sample."""

    flagged: bool
    reasoning: str
    raw_response: str


def get_model(model_name: str) -> Any:
    """Resolve an inspect_ai Model from a model name string.

    Supports any model string that inspect_ai accepts, e.g.:
    - "openai/gpt-4o-mini"
    - "anthropic/claude-sonnet-4-20250514"
    - "google/gemini-2.0-flash"
    """
    try:
        from inspect_ai.model import get_model as _get_model
    except ImportError:
        raise ImportError(
            "inspect_ai is required for LLM scanners. "
            "Install it with: pip install 'inspect-dataset[inspect]'"
        ) from None
    return _get_model(model_name)


async def judge_batch(
    model: Any,
    prompts: list[str],
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[LLMJudgment]:
    """Send a batch of prompts to the LLM and parse yes/no judgments.

    Each prompt should be crafted to elicit a response starting with YES or NO,
    followed by a brief explanation.

    Returns one LLMJudgment per prompt, in the same order.
    """
    from inspect_ai.model import ChatMessageSystem, ChatMessageUser

    sem = asyncio.Semaphore(concurrency)

    system_msg = ChatMessageSystem(
        content=(
            "You are a dataset quality auditor. Answer each question about an "
            "evaluation dataset sample. Always start your response with exactly "
            "YES or NO on the first line, then provide a brief explanation on "
            "the following lines."
        ),
    )

    async def _judge_one(prompt: str) -> LLMJudgment:
        async with sem:
            try:
                result = await model.generate([system_msg, ChatMessageUser(content=prompt)])
                text = result.completion.strip()
                first_line = text.split("\n")[0].strip().upper()
                flagged = first_line.startswith("YES")
                reasoning = "\n".join(text.split("\n")[1:]).strip()
                return LLMJudgment(
                    flagged=flagged,
                    reasoning=reasoning,
                    raw_response=text,
                )
            except Exception as e:
                logger.warning("LLM call failed: %s", e)
                return LLMJudgment(
                    flagged=False,
                    reasoning=f"LLM call failed: {e}",
                    raw_response="",
                )

    tasks = [_judge_one(p) for p in prompts]
    return list(await asyncio.gather(*tasks))
