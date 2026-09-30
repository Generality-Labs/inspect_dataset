from __future__ import annotations

import re
from dataclasses import dataclass

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id

_ARTICLES = frozenset({"a", "an", "the"})
_WORD = re.compile(r"[^\W_]+(?:['\u2019.-][^\W_]+)*")
# A sentence ends at a newline or after ".", "!" or "?", but not after an
# initial such as the "N." in "Leandro N. Alem".
_SENTENCE_BREAK = re.compile(r"\n+|(?<=[.!?])(?<!\b[A-Z]\.)\s+")
# Commas separate list items, so ", or" still offers the item before it. The
# other marks end an option outright. Commas and colons only count when
# followed by a space, so "1,000" and "10:30" stay whole.
_COMMA = ","
_STOP = "|"
_BOUNDARY = re.compile(r"(,)(?=\s|$)|[;:](?=\s|$)|[()\[\]{}\"\u201c\u201d?!]")
# Words that open a list of alternatives, so an option cannot extend past them.
_OPENERS = frozenset({"or", "either", "whether"})
_PHRASE_ENDS = _OPENERS | {_COMMA, _STOP}
_OPTION_TOKENS = 5


def _tokens(text: str) -> list[str]:
    """Lowercase word tokens with articles dropped, so punctuation and case do not matter."""
    return [t for t in _WORD.findall(text.lower()) if t not in _ARTICLES]


def _question_sentence(text: str) -> str | None:
    """Return the last sentence of ``text`` that ends in a question mark.

    Prompts often wrap the question in instructions, a passage or few-shot
    examples. Only the question itself offers options to the model.
    """
    for raw in reversed(_SENTENCE_BREAK.split(text)):
        sentence = raw.strip()
        if sentence.rstrip("\"'\u201d\u2019)]").endswith("?"):
            return sentence
    return None


@dataclass
class _Option:
    tokens: list[str]
    after_or: bool
    # The phrase stops at punctuation or the next "or", not at the token limit,
    # so its last token is a real phrase boundary (the head noun).
    complete: bool


def _stream(sentence: str) -> list[str]:
    """Tokenise ``sentence``, keeping comma and stop markers between words."""
    stream: list[str] = []
    pos = 0
    for m in _BOUNDARY.finditer(sentence):
        stream.extend(_tokens(sentence[pos : m.start()]))
        stream.append(_COMMA if m.group(1) else _STOP)
        pos = m.end()
    stream.extend(_tokens(sentence[pos:]))
    return stream


def _phrase_before(stream: list[str], end: int) -> tuple[list[str], int]:
    """Return the tokens before ``end`` back to a boundary, and the boundary index."""
    start = end
    while start > 0 and stream[start - 1] not in _PHRASE_ENDS:
        start -= 1
    return stream[start:end], start - 1


def _extract_or_options(sentence: str) -> list[_Option]:
    """Return the phrases on either side of each "or" in ``sentence``.

    For "is this an MRI or a CT scan?", returns "is this mri" before the "or"
    and "ct scan" after it. Each phrase holds at most a few tokens and stops
    at clause punctuation. In a list such as "A, B, or C", every item counts.
    """
    stream = _stream(sentence)
    options: list[_Option] = []
    for i, token in enumerate(stream):
        if token != "or":
            continue
        before, boundary = _phrase_before(stream, i)
        if before:
            options.append(_Option(before[-_OPTION_TOKENS:], after_or=False, complete=False))
        else:
            while boundary >= 0 and stream[boundary] == _COMMA:
                before, boundary = _phrase_before(stream, boundary)
                if before:
                    options.append(
                        _Option(before[-_OPTION_TOKENS:], after_or=False, complete=False)
                    )
        end = i + 1
        while end < len(stream) and stream[end] not in _PHRASE_ENDS:
            end += 1
        after = stream[i + 1 : end]
        if after:
            complete = len(after) <= _OPTION_TOKENS
            options.append(_Option(after[:_OPTION_TOKENS], after_or=True, complete=complete))
    return options


def _answer_matches_option(answer: list[str], option: _Option) -> bool:
    """Return True if the answer sits in the option at a token boundary.

    The answer must touch the "or" (the end of the phrase before it, the start
    of the phrase after it), or be the head noun that ends the phrase after it.
    """
    n = len(answer)
    o = option.tokens
    if n > len(o):
        return False
    if option.after_or:
        return o[:n] == answer or (option.complete and o[-n:] == answer)
    return o[-n:] == answer


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings = []
    for i, record in enumerate(records):
        question = str(record.get(fields.question, "") or "").strip()
        answer = str(record.get(fields.answer, "") or "").strip()

        answer_tokens = _tokens(answer)
        if not answer_tokens:
            continue

        sentence = _question_sentence(question)
        if sentence is None:
            continue

        options = _extract_or_options(sentence)
        if len(options) < 2:
            continue

        if any(_answer_matches_option(answer_tokens, o) for o in options):
            findings.append(
                Finding(
                    scanner="forced_choice_leakage",
                    severity="medium",
                    category="leakage",
                    explanation=(
                        f"Question explicitly offers the answer as one of its options "
                        f"('...or...'). A model can select the correct answer by "
                        f"pattern-matching the question without understanding the content. "
                        f"Question: {sentence!r}  Answer: {answer!r}"
                    ),
                    sample_index=i,
                    sample_id=get_sample_id(record, fields, i),
                    metadata={
                        "question": question,
                        "question_sentence": sentence,
                        "answer": answer,
                        "options": list(dict.fromkeys(" ".join(o.tokens) for o in options)),
                    },
                )
            )
    return findings


forced_choice_leakage = ScannerDef(
    name="forced_choice_leakage",
    fn=_scan,
    description=(
        "Flag questions that offer explicit options via 'or' where the answer "
        "is one of those options (e.g. 'is this an MRI or CT scan?' → 'mri'). "
        "A model can exploit the phrasing without understanding the content."
    ),
)
