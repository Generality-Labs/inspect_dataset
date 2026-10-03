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
    system_msg = ChatMessageSystem(content=_AUDITOR_SYSTEM)

    async def _judge_one(prompt: str) -> LLMJudgment:
        async with sem:
            return await _generate_judgment(model, [system_msg, ChatMessageUser(content=prompt)])

    tasks = [_judge_one(p) for p in prompts]
    return list(await asyncio.gather(*tasks))


async def judge_batch_vision(
    model: Any,
    prompts: list[str],
    images: list[bytes | None],
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[LLMJudgment]:
    """Like ``judge_batch`` but attaches a page image to each prompt.

    ``images`` is aligned with ``prompts``; an entry may be ``None`` (the prompt
    is then sent text-only). Image bytes are base64-encoded into a data URL and
    sent as an ``image`` content block ahead of the prompt text.
    """
    import base64

    from inspect_ai.model import (
        ChatMessageSystem,
        ChatMessageUser,
        ContentImage,
        ContentText,
    )

    sem = asyncio.Semaphore(concurrency)
    system_msg = ChatMessageSystem(content=_AUDITOR_SYSTEM)

    async def _judge_one(prompt: str, image: bytes | None) -> LLMJudgment:
        async with sem:
            if image is None:
                content: Any = prompt
            else:
                data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
                content = [ContentImage(image=data_url), ContentText(text=prompt)]
            return await _generate_judgment(model, [system_msg, ChatMessageUser(content=content)])

    tasks = [_judge_one(p, img) for p, img in zip(prompts, images, strict=True)]
    return list(await asyncio.gather(*tasks))


_AUDITOR_SYSTEM = (
    "You are a dataset quality auditor. Answer each question about an "
    "evaluation dataset sample. Always start your response with exactly "
    "YES or NO on the first line, then provide a brief explanation on "
    "the following lines."
)


async def _generate_judgment(model: Any, messages: list[Any]) -> LLMJudgment:
    try:
        result = await model.generate(messages)
        text = result.completion.strip()
        first_line = text.split("\n")[0].strip().upper()
        flagged = first_line.startswith("YES")
        reasoning = "\n".join(text.split("\n")[1:]).strip()
        return LLMJudgment(flagged=flagged, reasoning=reasoning, raw_response=text)
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        return LLMJudgment(flagged=False, reasoning=f"LLM call failed: {e}", raw_response="")
