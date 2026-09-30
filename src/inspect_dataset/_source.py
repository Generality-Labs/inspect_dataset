"""Join an inspect_ai task's samples to the raw dataset rows they came from.

While a task builds its dataset, ``capture_sources()`` records two things:

- every raw record that inspect_ai's ``hf_dataset``, ``csv_dataset`` and ``json_dataset``
  turn into samples, keyed by the ``Sample`` objects produced. This join is exact and
  survives shuffling and filtering.
- every ``datasets.load_dataset`` call and the table it returned, so that samples an eval
  builds by hand can be matched to a row by their id.

Both work by wrapping library functions. The wrappers are installed once and only record
while a capture is active; otherwise they pass straight through. ``data_to_samples`` is
private inspect_ai API, so if it moves, record-level joins stop and the id join remains.
Modules that imported ``load_dataset`` by name before the first capture keep the
unwrapped function, so their loads are not recorded.
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass, field
from typing import Any

SOURCE_FIELD = "__source__"

_LOAD_KWARGS = ("name", "split", "revision", "data_files", "data_dir")


@dataclass
class SourceInfo:
    """How a task's records were joined to their raw rows, for ``scan_summary.json``."""

    joined_by_record: int = 0
    joined_by_id: int = 0
    id_column: str | None = None
    total: int = 0
    loads: list[dict[str, Any]] = field(default_factory=list)

    def to_summary(self) -> dict[str, Any]:
        return {
            "field": SOURCE_FIELD,
            "joined": self.joined_by_record + self.joined_by_id,
            "total": self.total,
            "joined_by_record": self.joined_by_record,
            "joined_by_id": self.joined_by_id,
            "id_column": self.id_column,
            "loads": self.loads,
        }


@dataclass
class _Capture:
    # id(sample) -> (sample, raw row). Holding the sample keeps its id from being reused.
    rows: dict[int, tuple[Any, dict[str, Any]]] = field(default_factory=dict)
    tables: list[tuple[dict[str, Any], Any]] = field(default_factory=list)

    def row_for(self, sample: Any) -> dict[str, Any] | None:
        entry = self.rows.get(id(sample))
        return entry[1] if entry is not None and entry[0] is sample else None


_active: contextvars.ContextVar[_Capture | None] = contextvars.ContextVar(
    "inspect_dataset_source_capture", default=None
)


def _wrap_data_to_samples(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def data_to_samples(data: Any, data_to_sample: Callable[..., Any], auto_id: bool) -> Any:
        capture = _active.get()
        if capture is None:
            return original(data, data_to_sample, auto_id)

        def recording(record: Any) -> Any:
            # Snapshot first: record_to_sample functions often pop fields from the record
            raw = dict(record) if isinstance(record, Mapping) else {"value": record}
            produced = data_to_sample(record)
            for sample in produced if isinstance(produced, list) else [produced]:
                capture.rows[id(sample)] = (sample, raw)
            return produced

        return original(data, recording, auto_id)

    data_to_samples.__inspect_dataset_wrapped__ = True  # type: ignore[attr-defined]
    return data_to_samples


def _wrap_load_dataset(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def load_dataset(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        capture = _active.get()
        if capture is not None:
            capture.tables.append((_describe_load(args, kwargs), result))
        return result

    load_dataset.__inspect_dataset_wrapped__ = True  # type: ignore[attr-defined]
    return load_dataset


def _describe_load(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    described: dict[str, Any] = {"path": str(args[0] if args else kwargs.get("path"))}
    if len(args) > 1 and "name" not in kwargs:
        kwargs = {**kwargs, "name": args[1]}
    for key in _LOAD_KWARGS:
        if kwargs.get(key) is not None:
            value = kwargs[key]
            described[key] = value if isinstance(value, str | int) else str(value)
    return described


def _install() -> None:
    try:
        import inspect_ai.dataset._sources.csv as csv_source
        import inspect_ai.dataset._sources.hf as hf_source
        import inspect_ai.dataset._sources.json as json_source
    except ImportError:
        sources = []
    else:
        sources = [hf_source, csv_source, json_source]
    for module in sources:
        original = getattr(module, "data_to_samples", None)
        if original is not None and not getattr(original, "__inspect_dataset_wrapped__", False):
            module.data_to_samples = _wrap_data_to_samples(original)  # type: ignore[attr-defined]

    import datasets

    if not getattr(datasets.load_dataset, "__inspect_dataset_wrapped__", False):
        datasets.load_dataset = _wrap_load_dataset(datasets.load_dataset)  # type: ignore[assignment]


@contextlib.contextmanager
def capture_sources() -> Generator[_Capture]:
    """Record raw rows while a task builds its dataset. Nested captures share the outer one."""
    _install()
    outer = _active.get()
    if outer is not None:
        yield outer
        return
    capture = _Capture()
    token = _active.set(capture)
    try:
        yield capture
    finally:
        _active.reset(token)


def _tables(result: Any) -> list[Any]:
    import datasets

    if isinstance(result, datasets.DatasetDict):
        return list(result.values())
    if isinstance(result, datasets.Dataset):
        return [result]
    return []


def join_by_id(capture: _Capture, ids: list[Any]) -> tuple[str | None, dict[int, dict[str, Any]]]:
    """Match sample ids to a column of the tables loaded, returning (column, index -> row).

    A column is a candidate when its values are unique within each table and no value
    appears in two tables. The column matching the most ids wins, across all tables at
    once, so an eval that loads one table per subset still joins.
    """
    import datasets

    wanted = {str(i) for i in ids if i is not None}
    if not wanted:
        return None, {}
    by_column: dict[str, dict[str, tuple[Any, int]]] = {}
    ambiguous: set[str] = set()
    for table in (t for _, result in capture.tables for t in _tables(result)):
        for column, feature in table.features.items():
            if column in ambiguous or not isinstance(feature, datasets.Value):
                continue
            values = [str(v) for v in table[column]]
            if len(set(values)) != len(values):
                ambiguous.add(column)
                continue
            index = by_column.setdefault(column, {})
            for row, value in enumerate(values):
                if value in index:
                    ambiguous.add(column)
                    break
                index[value] = (table, row)
    candidates = {c: m for c, m in by_column.items() if c not in ambiguous}
    if not candidates:
        return None, {}
    column, index = max(candidates.items(), key=lambda item: len(wanted & item[1].keys()))
    matched: dict[int, dict[str, Any]] = {}
    for position, sample_id in enumerate(ids):
        hit = index.get(str(sample_id)) if sample_id is not None else None
        if hit is not None:
            table, row = hit
            matched[position] = dict(table[row])
    return (column, matched) if matched else (None, {})


def loads_of(capture: _Capture) -> list[dict[str, Any]]:
    """The distinct load_dataset calls made while the task built, in call order."""
    seen: list[dict[str, Any]] = []
    for load, _ in capture.tables:
        if load not in seen:
            seen.append(load)
    return seen
