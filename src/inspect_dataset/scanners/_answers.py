"""Answer values as the strings that the answer-text scanners measure.

Also checks whether the task's scorer compares answer text at all, and resolves a letter
answer, such as the target of a ``choice()``-scored task, to the text of the choice it names.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from inspect_dataset._types import FieldMap, Record
from inspect_dataset.scanner import ScannerNotApplicable

# Scorers that compare the answer text itself, so its length and format affect the score.
# Add a registry name here to run answer_length and inconsistent_format under that scorer.
VERBATIM_SCORERS = frozenset(
    {
        "inspect_ai/exact",
        "inspect_ai/match",
        "inspect_ai/includes",
        "inspect_ai/pattern",
    }
)


def require_verbatim_scorer(fields: FieldMap, scanner: str) -> None:
    """Check that the task's scorer compares answer text verbatim.

    Passes when the scorer is unknown (``fields.scorers`` is None, outside task mode) or when
    any of the task's scorers is in ``VERBATIM_SCORERS``.

    Raises:
        ScannerNotApplicable: if the task has no scorer, or none of its scorers compare text.
    """
    scorers = fields.scorers
    if scorers is None or any(s in VERBATIM_SCORERS for s in scorers):
        return
    assumption = f"{scanner} assumes a scorer that compares answer text verbatim"
    if not scorers:
        raise ScannerNotApplicable(f"{assumption}; this task has no scorer")
    raise ScannerNotApplicable(f"{assumption}; this task scores with {', '.join(scorers)}")


def is_scalar(value: Any) -> bool:
    """Whether a value is measured as text: anything but a list, dict, struct or array."""
    if isinstance(value, Mapping | list | tuple | set | frozenset):
        return False
    return getattr(value, "ndim", 0) == 0


def _as_list(value: Any) -> Any:
    """An array of one or more dimensions as a nested list, so it is handled like a list."""
    if getattr(value, "ndim", 0) >= 1 and hasattr(value, "tolist"):
        return value.tolist()
    return value


def _resolve(value: Any, path: list[str]) -> list[Any]:
    """Values at a dotted path, mapping over lists on the way. ``*`` selects the value itself."""
    value = _as_list(value)
    if isinstance(value, list | tuple):
        return [leaf for item in value for leaf in _resolve(item, path)]
    if not path:
        return [value]
    head, rest = path[0], path[1:]
    if head == "*":
        return _resolve(value, rest)
    if isinstance(value, Mapping) and head in value:
        return _resolve(value[head], rest)
    return []


def _hint(value: Any, subfield: str | None) -> str:
    action = (
        "pass --answer-subfield" if subfield is None else f"extend --answer-subfield {subfield!r}"
    )
    value = _as_list(value)
    if isinstance(value, list | tuple):
        first = next((v for v in value if v is not None), None)
        if isinstance(first, Mapping):
            keys = ", ".join(str(k) for k in first)
            return f"{action} with a key of its elements ({keys}) to measure each one"
        return f"{action} '*' to measure each element"
    if isinstance(value, Mapping):
        keys = ", ".join(str(k) for k in value)
        return f"{action} with one of its keys ({keys}) to measure the scalar inside it"
    return f"{action} with a path to a scalar inside it"


def answer_texts(records: list[Record], fields: FieldMap, scanner: str) -> list[list[str]]:
    """Each row's answer as stripped strings: one per row, or one per element under a subfield.

    Raises:
        ScannerNotApplicable: if any value to measure is a list, dict, struct or array, or if
            ``fields.answer_subfield`` matches nothing in any row.
    """
    subfield = fields.answer_subfield
    if subfield is None:
        values = [[record.get(fields.answer, "")] for record in records]
    else:
        path = subfield.split(".")
        values = [_resolve(record.get(fields.answer), path) for record in records]

    bad_rows = [row for row in values if not all(is_scalar(v) for v in row)]
    if bad_rows:
        label = fields.answer if subfield is None else f"{fields.answer}.{subfield}"
        types = Counter(type(v).__name__ for row in bad_rows for v in row if not is_scalar(v))
        first = next(v for v in bad_rows[0] if not is_scalar(v))
        raise ScannerNotApplicable(
            f"{scanner} measures scalar answers, but answer field {label!r} holds "
            f"{'/'.join(types)} values in {len(bad_rows):,} of {len(records):,} rows; "
            + _hint(first, subfield)
        )

    if subfield is not None and not any(values):
        raise ScannerNotApplicable(
            f"--answer-subfield {subfield!r} matched no value in answer field "
            f"{fields.answer!r} in any of {len(records):,} rows"
        )

    return [[str(v or "").strip() for v in row] for row in values]


def subfield_metadata(fields: FieldMap, element_index: int) -> dict[str, Any]:
    """Finding metadata locating the measured element; empty when no subfield is in use."""
    if fields.answer_subfield is None:
        return {}
    return {"answer_subfield": fields.answer_subfield, "element_index": element_index}


CHOICE_TEXT_NOTE = "measured as the choice text each target letter names"


def resolve_choice(answer: Any, choices: Any) -> str | None:
    """The choice text a letter answer names ("A" is the first choice), or None.

    Case and surrounding whitespace are ignored. None when the answer is not a single letter,
    the letter is past the last choice, or ``choices`` is not a list.
    """
    if not isinstance(answer, str) or not isinstance(choices, list | tuple):
        return None
    letter = answer.strip().upper()
    if len(letter) != 1 or not "A" <= letter <= "Z":
        return None
    index = ord(letter) - ord("A")
    if index >= len(choices):
        return None
    return str(choices[index])


def record_choices(record: Record, fields: FieldMap) -> Sequence[Any] | None:
    """The record's answer choices, or None when there is no choices field or no list in it."""
    if fields.choices is None:
        return None
    value = record.get(fields.choices)
    return value if isinstance(value, list | tuple) else None


def resolved_answer(record: Record, fields: FieldMap) -> Any:
    """The record's answer, with letter answers replaced by the choice text they name.

    A list answer is resolved element by element. Answers that do not resolve are returned as
    they are.
    """
    answer = record.get(fields.answer)
    choices = record_choices(record, fields)
    if choices is None:
        return answer
    if isinstance(answer, list | tuple):
        return [_resolve_or_keep(a, choices) for a in answer]
    return _resolve_or_keep(answer, choices)


def resolved_scalar_answer(record: Record, fields: FieldMap) -> Any:
    """The record's answer, with a letter answer replaced by the choice text it names.

    Unlike ``resolved_answer``, a list answer is returned as it is, matching ``choice_letters``.
    """
    return _resolve_or_keep(record.get(fields.answer), record_choices(record, fields) or ())


def choice_letters(records: list[Record], fields: FieldMap) -> list[str]:
    """Each row's target letter in upper case, or "" when it names none of the row's choices."""
    letters = []
    for record in records:
        answer = record.get(fields.answer)
        resolves = resolve_choice(answer, record_choices(record, fields)) is not None
        letters.append(str(answer).strip().upper() if resolves else "")
    return letters


def _resolve_or_keep(answer: Any, choices: Sequence[Any]) -> Any:
    text = resolve_choice(answer, choices)
    return answer if text is None else text
