from inspect_dataset._types import Category, FieldMap, Finding, ScanRun, Severity
from inspect_dataset._version import package_version
from inspect_dataset.scanner import (
    AnyScanner,
    AsyncDatasetScanner,
    DatasetScanner,
    LLMScannerDef,
    Requirement,
    ScannerDef,
    ScannerNotApplicable,
    dataset_scanner,
    run_scanners,
    run_scanners_async,
)

# The version is set once, in pyproject.toml; this reads it back from the
# installed package metadata.
__version__ = package_version()

__all__ = [
    "AnyScanner",
    "AsyncDatasetScanner",
    "Category",
    "DatasetScanner",
    "FieldMap",
    "Finding",
    "LLMScannerDef",
    "Requirement",
    "ScanRun",
    "ScannerDef",
    "ScannerNotApplicable",
    "Severity",
    "dataset_scanner",
    "run_scanners",
    "run_scanners_async",
]
