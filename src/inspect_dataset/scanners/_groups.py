"""Partition records into the subsets that the population scanners measure separately."""

from __future__ import annotations

from typing import Any

from inspect_dataset._types import FieldMap, Record
from inspect_dataset.scanner import ScannerNotApplicable

# Smallest group a distribution finding is made for. A balanced two-answer group of 20
# crosses the 85% imbalance threshold by chance 0.3% of the time; at 10 rows it is 2%.
MIN_GROUP_SIZE = 20


def group_rows(
    records: list[Record], fields: FieldMap, scanner: str
) -> list[tuple[Any, list[int]]]:
    """Row indices of each group, in order of first appearance.

    Without ``fields.group`` the whole dataset is one group. A row that lacks the group
    field belongs to the group ``None``.

    Raises:
        ScannerNotApplicable: if a group value is a list, dict or other unhashable value.
    """
    if fields.group is None:
        return [(None, list(range(len(records))))]
    rows: dict[Any, list[int]] = {}
    for i, record in enumerate(records):
        value = record.get(fields.group)
        try:
            rows.setdefault(value, []).append(i)
        except TypeError:
            raise ScannerNotApplicable(
                f"{scanner} groups rows by {fields.group!r}, but it holds "
                f"{type(value).__name__} values; group by a field with scalar values"
            ) from None
    return list(rows.items())


def population_groups(
    records: list[Record], fields: FieldMap, scanner: str, answers: list[str]
) -> list[tuple[Any, list[str]]]:
    """Non-empty answers of each group that a distribution scanner should measure.

    Without grouping this is every non-empty answer, as one group. With grouping, groups
    with fewer than ``MIN_GROUP_SIZE`` non-empty answers are left out.

    Raises:
        ScannerNotApplicable: if grouping leaves out every group.
    """
    groups = [
        (value, [answers[i] for i in rows if answers[i]])
        for value, rows in group_rows(records, fields, scanner)
    ]
    groups = [(value, non_empty) for value, non_empty in groups if non_empty]
    if fields.group is None or not groups:
        return groups
    measured = [
        (value, non_empty) for value, non_empty in groups if len(non_empty) >= MIN_GROUP_SIZE
    ]
    if not measured:
        largest = max(len(non_empty) for _, non_empty in groups)
        raise ScannerNotApplicable(
            f"{scanner} needs at least {MIN_GROUP_SIZE} answers in a group, but every group "
            f"of {fields.group!r} has fewer than {MIN_GROUP_SIZE} (largest: {largest})"
        )
    return measured


def group_label(fields: FieldMap, value: Any) -> str:
    """How a finding's explanation names its group, e.g. ``subject='law'``."""
    return f"{fields.group}={value!r}"


def group_metadata(fields: FieldMap, value: Any) -> dict[str, Any]:
    """Finding metadata naming the group; empty when grouping is off."""
    if fields.group is None:
        return {}
    return {"group": value}
