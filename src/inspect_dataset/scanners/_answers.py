"""Answer values as the strings that the answer-text scanners measure."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from inspect_dataset._types import FieldMap, Record
from inspect_dataset.scanner import ScannerNotApplicable


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
