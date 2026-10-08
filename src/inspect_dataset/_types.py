from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["low", "medium", "high"]
Category = Literal["label_quality", "question_quality", "distribution", "format", "leakage"]

Record = dict[str, Any]


@dataclass
class FieldMap:
    """Resolved mapping from logical field roles to dataset column names.

    Besides the column roles, it carries dataset-level context that scanners may use, such as
    the column holding each sample's answer choices and the scorers of the inspect_ai task
    the records came from. ``group`` names the record field whose value is each sample's
    subset. The population scanners (``inconsistent_format``, ``answer_distribution``,
    ``binary_question_ratio``) compute their statistics per group when it is set.
    """

    question: str
    answer: str
    id: str | None = None
    image: str | None = None
    # Dotted path to the scalar inside a non-scalar answer column, for the answer-text scanners.
    answer_subfield: str | None = None
    group: str | None = None
    # Column holding each sample's list of answer choices, which a letter answer indexes into.
    choices: str | None = None
    # Registry names of the task's scorers (e.g. "inspect_ai/choice"). None outside task mode.
    scorers: list[str] | None = None
    # Where the records came from: "hf", "inspect_task" or "local" (annotation files), as the
    # run records it. Set by the scanner runner; None when a scanner is called directly.
    source_type: str | None = None


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
    group_by: str | None = None  # FieldMap.group the population scanners grouped by
    group_by_source: str | None = None  # how group_by was chosen: "option" | "auto" | None
    # scanner name → {"status": "ran"} or {"status": "not_applicable", "reason": ...}
    scanner_status: dict[str, dict[str, str]] = field(default_factory=dict)
    task: str | None = None  # task spec as given on the command line (task mode)
    scorers: list[str] | None = None  # the task's scorer registry names (task mode)
    # HF mode: whether split/config were filled in rather than given. None for other sources.
    split_defaulted: bool | None = None
    config_defaulted: bool | None = None
    # Task mode: how records were joined to their raw rows (SourceInfo.to_summary()).
    source: dict[str, Any] | None = None

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
