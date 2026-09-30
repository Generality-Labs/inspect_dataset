from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Iterable, Mapping
from typing import Any, Literal, get_args

from inspect_dataset._types import FieldMap, Finding, Record, ScanRun

DatasetScanner = Callable[[list[Record], FieldMap], list[Finding]]
AsyncDatasetScanner = Callable[[list[Record], FieldMap], Coroutine[Any, Any, list[Finding]]]


class ScannerNotApplicable(Exception):  # noqa: N818 -- a status, not an error
    """Raised by a scanner whose check does not apply to this dataset.

    The runner records the scanner as ``not_applicable`` with ``reason`` in
    ``ScanRun.scanner_status``, instead of recording zero findings.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


Requirement = Literal["answer", "image", "artifacts"]
"""An input a scanner needs. The runner checks each one before calling the scanner.

- ``answer``: at least one row has a non-empty value in the answer field.
- ``image``: an image field is set and at least one row has a value in it.
- ``artifacts``: at least one row has an extraction artifacts directory (``--files-root``).
"""

_REQUIREMENTS: tuple[Requirement, ...] = get_args(Requirement)


def _validate_requires(requires: Requirement | Iterable[Requirement]) -> tuple[Requirement, ...]:
    names = (requires,) if isinstance(requires, str) else tuple(requires)
    unknown = [n for n in names if n not in _REQUIREMENTS]
    if unknown:
        raise ValueError(
            f"unknown scanner requirement(s) {', '.join(map(repr, unknown))}; "
            f"expected one of {', '.join(map(repr, _REQUIREMENTS))}"
        )
    return tuple(dict.fromkeys(names))


class ScannerDef:
    """A named scanner with metadata.

    ``requires`` names the inputs the scanner needs (see ``Requirement``). When one is
    missing, the runner records the scanner as ``not_applicable`` without calling it.
    """

    def __init__(
        self,
        name: str,
        fn: DatasetScanner,
        description: str = "",
        requires: Requirement | Iterable[Requirement] = (),
    ) -> None:
        self.name = name
        self.fn = fn
        self.description = description
        self.requires = _validate_requires(requires)

    def __call__(self, records: list[Record], fields: FieldMap) -> list[Finding]:
        return self.fn(records, fields)


class LLMScannerDef:
    """An async scanner that requires an LLM model. ``requires`` works as for ``ScannerDef``."""

    def __init__(
        self,
        name: str,
        fn: AsyncDatasetScanner,
        description: str = "",
        requires: Requirement | Iterable[Requirement] = (),
    ) -> None:
        self.name = name
        self.fn = fn
        self.description = description
        self.requires = _validate_requires(requires)

    async def __call__(self, records: list[Record], fields: FieldMap) -> list[Finding]:
        return await self.fn(records, fields)


def dataset_scanner(
    description: str = "",
    requires: Requirement | Iterable[Requirement] = (),
) -> Callable[[DatasetScanner], ScannerDef]:
    """Decorator that wraps a scanner function into a ScannerDef.

    Usage::

        @dataset_scanner(description="Flag long answers", requires=["answer"])
        def answer_length(records, fields):
            ...
    """
    requires = _validate_requires(requires)

    def decorator(fn: DatasetScanner) -> ScannerDef:
        return ScannerDef(name=fn.__name__, fn=fn, description=description, requires=requires)

    return decorator


AnyScanner = ScannerDef | LLMScannerDef


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, Mapping | list | tuple | set | frozenset):
        return not value
    return getattr(value, "size", 1) == 0


def _unmet_requirements(
    records: list[Record], fields: FieldMap, source_type: str
) -> dict[Requirement, str]:
    """The reason each unmet requirement gives for a scanner not applying."""
    unmet: dict[Requirement, str] = {}
    if all(_is_empty(r.get(fields.answer)) for r in records):
        unmet["answer"] = f"no non-empty answers in field {fields.answer!r}"
    if fields.image is None:
        unmet["image"] = (
            "no image field; task scans do not load images from sample input yet"
            if source_type == "inspect_task"
            else "no image field; pass --image-field"
        )
    elif all(r.get(fields.image) is None for r in records):
        unmet["image"] = f"image field {fields.image!r} is empty in every row"
    if not any(r.get("__artifacts_dir__") for r in records):
        unmet["artifacts"] = (
            "no extraction artifacts; pass --files-root with one directory per sample id"
        )
    return unmet


def _not_applicable_reason(scanner: AnyScanner, unmet: dict[Requirement, str]) -> str | None:
    return next((unmet[r] for r in scanner.requires if r in unmet), None)


def run_scanners(
    records: list[Record],
    fields: FieldMap,
    scanners: list[AnyScanner],
    dataset_name: str = "",
    split: str | None = None,
    source_type: str = "hf",
    revision: str | None = None,
    config: str | None = None,
    group_by_source: str | None = None,
    task: str | None = None,
) -> ScanRun:
    """Run scanners synchronously. Raises if any LLM scanners are included.

    ``ScanRun.group_by`` is taken from ``fields.group``. ``group_by_source`` says how it
    was chosen (``"option"`` or ``"auto"``) and is dropped when there is no group. It is
    not inferred: ``fields`` from ``load_inspect_task`` may already carry a detected
    group, and the run then records ``group_by_source=None`` unless the caller passes it.

    The run records ``fields.scorers``, the scorers the scanners saw.
    """
    llm = [s for s in scanners if isinstance(s, LLMScannerDef)]
    if llm:
        raise TypeError(
            f"LLM scanners ({', '.join(s.name for s in llm)}) require async execution. "
            "Use run_scanners_async() instead."
        )
    all_findings: list[Finding] = []
    status: dict[str, dict[str, str]] = {}
    unmet = _unmet_requirements(records, fields, source_type)
    for scanner in scanners:
        assert isinstance(scanner, ScannerDef)
        reason = _not_applicable_reason(scanner, unmet)
        if reason is not None:
            status[scanner.name] = {"status": "not_applicable", "reason": reason}
            continue
        try:
            findings = scanner(records, fields)
        except ScannerNotApplicable as e:
            findings = []
            status[scanner.name] = {"status": "not_applicable", "reason": e.reason}
        else:
            status[scanner.name] = {"status": "ran"}
        # Ensure scanner name is stamped on every finding
        for f in findings:
            f.scanner = scanner.name
        all_findings.extend(findings)
    return ScanRun(
        dataset_name=dataset_name,
        split=split,
        total_samples=len(records),
        findings=all_findings,
        source_type=source_type,
        revision=revision,
        config=config,
        group_by=fields.group,
        group_by_source=group_by_source if fields.group is not None else None,
        scanner_status=status,
        task=task,
        scorers=fields.scorers,
    )


async def run_scanners_async(
    records: list[Record],
    fields: FieldMap,
    scanners: list[AnyScanner],
    dataset_name: str = "",
    split: str | None = None,
    source_type: str = "hf",
    revision: str | None = None,
    config: str | None = None,
    group_by_source: str | None = None,
    task: str | None = None,
) -> ScanRun:
    """Run scanners, supporting both sync and async (LLM) scanners."""
    # Run sync scanners first
    sync_scanners = [s for s in scanners if isinstance(s, ScannerDef)]
    run = run_scanners(
        records,
        fields,
        list(sync_scanners),
        dataset_name=dataset_name,
        split=split,
        source_type=source_type,
        revision=revision,
        config=config,
        group_by_source=group_by_source,
        task=task,
    )

    # Run async (LLM) scanners concurrently
    async_scanners: list[LLMScannerDef] = []
    unmet = _unmet_requirements(records, fields, source_type)
    for s in scanners:
        if not isinstance(s, LLMScannerDef):
            continue
        reason = _not_applicable_reason(s, unmet)
        if reason is None:
            async_scanners.append(s)
        else:
            run.scanner_status[s.name] = {"status": "not_applicable", "reason": reason}
    if async_scanners:

        async def _guarded(scanner: LLMScannerDef) -> list[Finding] | ScannerNotApplicable:
            try:
                return await scanner(records, fields)
            except ScannerNotApplicable as e:
                return e

        results = await asyncio.gather(*(_guarded(s) for s in async_scanners))
        for llm_scanner, result in zip(async_scanners, results, strict=True):
            if isinstance(result, ScannerNotApplicable):
                run.scanner_status[llm_scanner.name] = {
                    "status": "not_applicable",
                    "reason": result.reason,
                }
                continue
            run.scanner_status[llm_scanner.name] = {"status": "ran"}
            for f in result:
                f.scanner = llm_scanner.name
            run.findings.extend(result)

    return run


def get_field_value(record: Record, field_name: str) -> Any:
    return record.get(field_name)


def get_sample_id(record: Record, fields: FieldMap, index: int) -> str | int | None:
    if fields.id is not None:
        return record.get(fields.id)
    return index
