from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from inspect_dataset._types import FieldMap, Finding, Record, ScanRun

DatasetScanner = Callable[[list[Record], FieldMap], list[Finding]]
AsyncDatasetScanner = Callable[[list[Record], FieldMap], Coroutine[Any, Any, list[Finding]]]


class ScannerDef:
    """A named scanner with metadata."""

    def __init__(
        self,
        name: str,
        fn: DatasetScanner,
        description: str = "",
    ) -> None:
        self.name = name
        self.fn = fn
        self.description = description

    def __call__(self, records: list[Record], fields: FieldMap) -> list[Finding]:
        return self.fn(records, fields)


class LLMScannerDef:
    """An async scanner that requires an LLM model."""

    def __init__(
        self,
        name: str,
        fn: AsyncDatasetScanner,
        description: str = "",
    ) -> None:
        self.name = name
        self.fn = fn
        self.description = description

    async def __call__(self, records: list[Record], fields: FieldMap) -> list[Finding]:
        return await self.fn(records, fields)


def dataset_scanner(
    description: str = "",
) -> Callable[[DatasetScanner], ScannerDef]:
    """Decorator that wraps a scanner function into a ScannerDef.

    Usage::

        @dataset_scanner(description="Flag long answers")
        def answer_length(records, fields):
            ...
    """

    def decorator(fn: DatasetScanner) -> ScannerDef:
        return ScannerDef(name=fn.__name__, fn=fn, description=description)

    return decorator


AnyScanner = ScannerDef | LLMScannerDef


def run_scanners(
    records: list[Record],
    fields: FieldMap,
    scanners: list[AnyScanner],
    dataset_name: str = "",
    split: str | None = None,
    source_type: str = "hf",
    revision: str | None = None,
) -> ScanRun:
    """Run scanners synchronously. Raises if any LLM scanners are included."""
    llm = [s for s in scanners if isinstance(s, LLMScannerDef)]
    if llm:
        raise TypeError(
            f"LLM scanners ({', '.join(s.name for s in llm)}) require async execution. "
            "Use run_scanners_async() instead."
        )
    all_findings: list[Finding] = []
    for scanner in scanners:
        assert isinstance(scanner, ScannerDef)
        findings = scanner(records, fields)
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
    )


async def run_scanners_async(
    records: list[Record],
    fields: FieldMap,
    scanners: list[AnyScanner],
    dataset_name: str = "",
    split: str | None = None,
    source_type: str = "hf",
    revision: str | None = None,
) -> ScanRun:
    """Run scanners, supporting both sync and async (LLM) scanners."""
    all_findings: list[Finding] = []

    # Run sync scanners first
    sync_scanners = [s for s in scanners if isinstance(s, ScannerDef)]
    for scanner in sync_scanners:
        findings = scanner(records, fields)
        for f in findings:
            f.scanner = scanner.name
        all_findings.extend(findings)

    # Run async (LLM) scanners concurrently
    async_scanners = [s for s in scanners if isinstance(s, LLMScannerDef)]
    if async_scanners:
        tasks = [s(records, fields) for s in async_scanners]
        results = await asyncio.gather(*tasks)
        for llm_scanner, findings in zip(async_scanners, results, strict=True):
            for f in findings:
                f.scanner = llm_scanner.name
            all_findings.extend(findings)

    return ScanRun(
        dataset_name=dataset_name,
        split=split,
        total_samples=len(records),
        findings=all_findings,
        source_type=source_type,
        revision=revision,
    )


def get_field_value(record: Record, field_name: str) -> Any:
    return record.get(field_name)


def get_sample_id(record: Record, fields: FieldMap, index: int) -> str | int | None:
    if fields.id is not None:
        return record.get(fields.id)
    return index
