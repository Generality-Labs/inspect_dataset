from collections.abc import Callable

from inspect_dataset.scanner import LLMScannerDef, ScannerDef
from inspect_dataset.scanners.ambiguity import _make_scanner as _make_ambiguity
from inspect_dataset.scanners.answer_distribution import answer_distribution
from inspect_dataset.scanners.answer_length import answer_length
from inspect_dataset.scanners.answerability import (
    _make_scanner as _make_answerability,
)
from inspect_dataset.scanners.binary_question_ratio import binary_question_ratio
from inspect_dataset.scanners.duplicate_questions import duplicate_questions
from inspect_dataset.scanners.encoding_issues import encoding_issues
from inspect_dataset.scanners.extraction_artifacts import extraction_artifacts
from inspect_dataset.scanners.forced_choice_leakage import forced_choice_leakage
from inspect_dataset.scanners.gold_fidelity import (
    _make_scanner as _make_gold_fidelity,
)
from inspect_dataset.scanners.image_mime_type import image_mime_type
from inspect_dataset.scanners.inconsistent_format import inconsistent_format
from inspect_dataset.scanners.label_correctness import (
    _make_scanner as _make_label_correctness,
)
from inspect_dataset.scanners.markdown_integrity import markdown_integrity
from inspect_dataset.scanners.numeric_provenance import numeric_provenance
from inspect_dataset.scanners.text_layer_recall import text_layer_recall

BUILTIN_SCANNERS: list[ScannerDef] = [
    answer_length,
    duplicate_questions,
    inconsistent_format,
    answer_distribution,
    forced_choice_leakage,
    encoding_issues,
    binary_question_ratio,
    image_mime_type,
    markdown_integrity,
    extraction_artifacts,
    text_layer_recall,
    numeric_provenance,
]

BUILTIN_SCANNER_NAMES: dict[str, ScannerDef] = {s.name: s for s in BUILTIN_SCANNERS}

# LLM scanner factories: name → callable(model_name) → LLMScannerDef
LLM_SCANNER_FACTORIES: dict[str, Callable[..., LLMScannerDef]] = {
    "ambiguity": _make_ambiguity,
    "label_correctness": _make_label_correctness,
    "answerability": _make_answerability,
    "gold_fidelity": _make_gold_fidelity,
}

ALL_SCANNER_NAMES: set[str] = set(BUILTIN_SCANNER_NAMES) | set(LLM_SCANNER_FACTORIES)
