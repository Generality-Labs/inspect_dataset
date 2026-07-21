from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["low", "medium", "high"]
Category = Literal["label_quality", "question_quality", "distribution", "format", "leakage"]

Record = dict[str, Any]


@dataclass
class FieldMap:
    """Resolved mapping from logical field roles to dataset column names."""

    question: str
    answer: str
    id: str | None = None
    image: str | None = None


@dataclass
class Finding:
    scanner: str
    severity: Severity
    category: Category
    explanation: str
    sample_index: int
    sample_id: str | int | None = None
    line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanner": self.scanner,
            "severity": self.severity,
            "category": self.category,
            "explanation": self.explanation,
            "sample_index": self.sample_index,
            "sample_id": self.sample_id,
            "line": self.line,
            "metadata": self.metadata,
        }


@dataclass
class ScanRun:
    """Result of running all scanners over a dataset."""

    dataset_name: str
    split: str | None
    total_samples: int
    findings: list[Finding]
    source_type: str = "hf"  # "hf" | "inspect_task"
    revision: str | None = None  # HF revision / commit SHA
    config: str | None = None  # HF config/subset name (multi-config datasets)

    def by_scanner(self) -> dict[str, list[Finding]]:
        result: dict[str, list[Finding]] = {}
        for f in self.findings:
            result.setdefault(f.scanner, []).append(f)
        return result

    def by_severity(self) -> dict[str, list[Finding]]:
        result: dict[str, list[Finding]] = {}
        for f in self.findings:
            result.setdefault(f.severity, []).append(f)
        return result
