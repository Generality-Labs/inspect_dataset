"""Join an inspect_ai task's samples to the raw dataset rows they came from.

While a task builds its dataset, ``capture_sources()`` records:

- every raw record that inspect_ai converts into samples, keyed by the ``Sample`` objects
  produced. inspect_ai's ``hf_dataset``, ``csv_dataset`` and ``json_dataset`` all build
  their converter with ``record_to_sample_fn``, and helpers that convert records
  themselves go through ``data_to_samples``. This join is exact and survives shuffling,
  filtering and ``Sample.model_copy``.
- every ``datasets.load_dataset`` and ``hf_dataset`` call, with the tables
  ``load_dataset`` returned. Samples an eval builds by hand are matched to a row of those
  tables by id, and a match only counts when the row's text also appears in the sample.

Both work by wrapping library functions, including every module-level binding of them made
by ``from ... import``. The wrappers only record while a capture is active; otherwise they
pass their arguments straight through. ``record_to_sample_fn`` and ``data_to_samples`` are
private inspect_ai API, so if they move, record-level joins stop and the id join remains.
"""

from __future__ import annotations

import contextlib
import contextvars
import copy
import functools
import inspect
import sys
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass, field
from typing import Any

SOURCE_FIELD = "__source__"

_LOAD_ARGUMENTS = ("path", "name", "split", "revision", "data_files", "data_dir")
# A raw string shorter than this is too common to show that a row belongs to a sample
_MIN_EVIDENCE_CHARS = 4
# How many of the best-matching id columns to verify by content before giving up
_ID_COLUMNS_TO_VERIFY = 3


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
    tables: list[Any] = field(default_factory=list)
    loads: list[dict[str, Any]] = field(default_factory=list)

    def row_for(self, sample: Any) -> dict[str, Any] | None:
        entry = self.rows.get(id(sample))
        return entry[1] if entry is not None and entry[0] is sample else None


_active: contextvars.ContextVar[_Capture | None] = contextvars.ContextVar(
    "inspect_dataset_source_capture", default=None
)


# ---------------------------------------------------------------------------
# Wrappers
# ---------------------------------------------------------------------------


def _recording(convert: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a record-to-sample converter so each sample it makes is mapped to its record."""
    if getattr(convert, "__inspect_dataset_recording__", False):
        return convert

    @functools.wraps(convert)
    def record_to_sample(record: Any) -> Any:
        capture = _active.get()
        if capture is None:
            return convert(record)
        # A deep snapshot, because converters often pop or reorder fields in place.
        # Immutable values such as image bytes are shared, not copied.
        raw = copy.deepcopy(dict(record)) if isinstance(record, Mapping) else {"value": record}
        produced = convert(record)
        for sample in produced if isinstance(produced, list) else [produced]:
            capture.rows[id(sample)] = (sample, raw)
        return produced

    record_to_sample.__inspect_dataset_recording__ = True  # type: ignore[attr-defined]
    return record_to_sample


def _wrap_record_to_sample_fn(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def record_to_sample_fn(*args: Any, **kwargs: Any) -> Any:
        return _recording(record_to_sample_fn.__wrapped__(*args, **kwargs))

    return _mark(record_to_sample_fn)


def _wrap_data_to_samples(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def data_to_samples(*args: Any, **kwargs: Any) -> Any:
        if _active.get() is not None:
            if callable(kwargs.get("data_to_sample")):
                kwargs["data_to_sample"] = _recording(kwargs["data_to_sample"])
            elif len(args) > 1 and callable(args[1]):
                args = (args[0], _recording(args[1]), *args[2:])
        return data_to_samples.__wrapped__(*args, **kwargs)

    return _mark(data_to_samples)


def _wrap_load_dataset(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def load_dataset(*args: Any, **kwargs: Any) -> Any:
        result = load_dataset.__wrapped__(*args, **kwargs)
        capture = _active.get()
        if capture is not None:
            capture.loads.append(_describe_call(original, args, kwargs))
            capture.tables.extend(_tables(result))
        return result

    return _mark(load_dataset)


def _wrap_hf_dataset(original: Callable[..., Any]) -> Callable[..., Any]:
    # inspect_ai's hf_dataset reads its own disk cache on repeat loads and then never
    # calls load_dataset, so record the call itself for provenance
    @functools.wraps(original)
    def hf_dataset(*args: Any, **kwargs: Any) -> Any:
        capture = _active.get()
        if capture is not None:
            capture.loads.append(_describe_call(original, args, kwargs))
        return hf_dataset.__wrapped__(*args, **kwargs)

    return _mark(hf_dataset)


def _wrap_model_copy(original: Callable[..., Any]) -> Callable[..., Any]:
    # Evals that rename ids or add sandboxes copy each sample; the copy keeps its row
    @functools.wraps(original)
    def model_copy(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = model_copy.__wrapped__(self, *args, **kwargs)
        capture = _active.get()
        if capture is not None and (raw := capture.row_for(self)) is not None:
            capture.rows[id(result)] = (result, raw)
        return result

    return _mark(model_copy)


def _mark(wrapper: Callable[..., Any]) -> Callable[..., Any]:
    wrapper.__inspect_dataset_wrapped__ = True  # type: ignore[attr-defined]
    return wrapper


def _describe_call(
    function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    """The path, config, split, revision and data files of a dataset load."""
    try:
        arguments = dict(inspect.signature(function).bind_partial(*args, **kwargs).arguments)
    except (TypeError, ValueError):
        arguments = {"path": args[0] if args else kwargs.get("path"), **kwargs}
    for name, value in list(arguments.items()):
        if isinstance(value, dict) and name not in _LOAD_ARGUMENTS:
            arguments.update(value)  # a **kwargs catch-all
    described: dict[str, Any] = {}
    for key in _LOAD_ARGUMENTS:
        value = arguments.get(key)
        if value is not None:
            described[key] = value if isinstance(value, str | int) else str(value)
    return described


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

# (name, id(original)) -> (original, wrapper), so a function is only ever wrapped once
_wrapped: dict[tuple[str, int], tuple[Callable[..., Any], Callable[..., Any]]] = {}


def _wrap_everywhere(
    home: Any, name: str, wrap: Callable[[Callable[..., Any]], Callable[..., Any]]
) -> None:
    """Wrap ``home.<name>`` and every module-level binding of the same function object.

    Evals and helpers often import these functions by name (``from datasets import
    load_dataset``), which copies the reference at import time, so wrapping only the home
    module would miss them. Module dicts are read directly so lazy modules are not triggered.
    """
    current = home.__dict__.get(name)
    if current is None:
        return
    if not getattr(current, "__inspect_dataset_wrapped__", False):
        _wrapped.setdefault((name, id(current)), (current, wrap(current)))
    for module in list(sys.modules.values()):
        bound = getattr(module, "__dict__", {}).get(name)
        pair = _wrapped.get((name, id(bound))) if bound is not None else None
        if pair is not None and bound is pair[0]:
            setattr(module, name, pair[1])


def _install() -> None:
    try:
        import inspect_ai.dataset._sources.hf as hf_source
        from inspect_ai.dataset import Sample, _util
    except ImportError:
        pass
    else:
        _wrap_everywhere(_util, "record_to_sample_fn", _wrap_record_to_sample_fn)
        _wrap_everywhere(_util, "data_to_samples", _wrap_data_to_samples)
        _wrap_everywhere(hf_source, "hf_dataset", _wrap_hf_dataset)
        if not getattr(Sample.model_copy, "__inspect_dataset_wrapped__", False):
            Sample.model_copy = _wrap_model_copy(Sample.model_copy)  # type: ignore[method-assign]

    import datasets

    _wrap_everywhere(datasets, "load_dataset", _wrap_load_dataset)


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


# ---------------------------------------------------------------------------
# Id join
# ---------------------------------------------------------------------------


def _tables(result: Any) -> list[Any]:
    import datasets

    if isinstance(result, datasets.DatasetDict):
        return list(result.values())
    if isinstance(result, datasets.Dataset):
        return [result]
    return []


def _normalise(text: str) -> str:
    return " ".join(text.split()).lower()


def row_supports(row: Mapping[str, Any], record: Mapping[str, Any]) -> bool:
    """Whether some text of a raw row appears in the sample's input, targets or choices."""
    haystacks = [
        _normalise(str(value))
        for value in (
            record.get("input"),
            *(record.get("targets") or []),
            *(record.get("choices") or []),
        )
        if value
    ]
    for value in row.values():
        if (
            isinstance(value, str)
            and len(text := _normalise(value)) >= _MIN_EVIDENCE_CHARS
            and any(text in haystack for haystack in haystacks)
        ):
            return True
    return False


def join_by_id(
    capture: _Capture, records: list[Mapping[str, Any]]
) -> tuple[str | None, dict[int, dict[str, Any]]]:
    """Match records to rows of the loaded tables by id, returning (column, index -> row).

    A column is a candidate when it holds scalar values that are unique within each table
    and across tables. Candidates are ranked by how many ids they match, across all tables
    at once, so an eval that loads one table per subset still joins. A match only counts
    when ``row_supports`` finds the row's text in the sample; the best of the top
    candidates by that count wins. Matching runs in Arrow, so large tables are not
    converted to Python.
    """
    import datasets
    import pyarrow as pa
    import pyarrow.compute

    # pyarrow's stubs omit its generated compute functions (is_in, count_distinct, ...)
    pc: Any = pyarrow.compute

    ids = [None if r.get("id") is None else str(r["id"]) for r in records]
    wanted = pa.array(sorted({i for i in ids if i is not None}), type=pa.string())
    if not len(wanted):
        return None, {}

    # column -> value -> (table index, row index)
    by_column: dict[str, dict[str, tuple[int, int]]] = {}
    ambiguous: set[str] = set()
    for t, table in enumerate(capture.tables):
        arrow = table.with_format("arrow")
        for column, feature in table.features.items():
            if column in ambiguous or not isinstance(feature, datasets.Value):
                continue
            try:
                values = pc.cast(arrow[column], pa.string())
            except (pa.ArrowInvalid, pa.ArrowNotImplementedError):
                continue
            hits = pc.indices_nonzero(pc.is_in(values, value_set=wanted)).to_pylist()
            if not hits:
                continue
            if pc.count_distinct(values, mode="all").as_py() != len(values):
                ambiguous.add(column)
                continue
            index = by_column.setdefault(column, {})
            for row, value in zip(hits, pc.take(values, hits).to_pylist(), strict=True):
                if value in index:
                    ambiguous.add(column)
                    break
                index[value] = (t, row)

    ranked = sorted(
        ((c, m) for c, m in by_column.items() if c not in ambiguous),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    best: tuple[str | None, dict[int, dict[str, Any]]] = (None, {})
    for column, index in ranked[:_ID_COLUMNS_TO_VERIFY]:
        positions = [(p, index[i]) for p, i in enumerate(ids) if i is not None and i in index]
        rows = _fetch_rows(capture, [hit for _, hit in positions])
        verified = {p: rows[hit] for p, hit in positions if row_supports(rows[hit], records[p])}
        if len(verified) > len(best[1]):
            best = (column, verified)
    return best


def _fetch_rows(
    capture: _Capture, hits: list[tuple[int, int]]
) -> dict[tuple[int, int], dict[str, Any]]:
    """Rows as plain dicts, with images as ``{"bytes", "path"}`` like record-level joins."""
    import datasets

    by_table: dict[int, list[int]] = {}
    for t, row in hits:
        by_table.setdefault(t, []).append(row)
    fetched: dict[tuple[int, int], dict[str, Any]] = {}
    for t, rows in by_table.items():
        table = capture.tables[t]
        for column, feature in table.features.items():
            if isinstance(feature, datasets.Image) and feature.decode:
                table = table.cast_column(column, datasets.Image(decode=False))
        for row, values in zip(rows, table.select(rows).to_list(), strict=True):
            fetched[(t, row)] = values
    return fetched


def loads_of(capture: _Capture) -> list[dict[str, Any]]:
    """The distinct dataset loads made while the task built, in call order."""
    seen: list[dict[str, Any]] = []
    for load in capture.loads:
        if load not in seen:
            seen.append(load)
    return seen
