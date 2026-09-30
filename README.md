# inspect-dataset

Dataset quality scanner for AI evaluation benchmarks. Companion to [inspect-scout](https://github.com/meridian-labs/inspect-scout), which analyses agent trajectories — inspect-dataset audits the underlying datasets themselves.

## Installation

```bash
pip install inspect-dataset
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add inspect-dataset
```

## Usage

````bash
# Scan a HuggingFace dataset
inspect-dataset scan flaviagiammarino/vqa-rad --split test -o findings/

# Pick a config and split (needed when the dataset has several configs, or several splits and none is "train")
inspect-dataset scan allenai/ai2_arc --config ARC-Challenge --split test -o findings/

# Pin to a specific revision
inspect-dataset scan flaviagiammarino/vqa-rad --revision abc123 -o findings/

# Override auto-detected field names
inspect-dataset scan my-org/my-dataset \
  --question-field prompt \
  --answer-field label \
  -o findings/

# Run only specific scanners
inspect-dataset scan flaviagiammarino/vqa-rad \
  --scanners answer_length,duplicate_questions

# Adjust answer length threshold (default: 4 words)
inspect-dataset scan flaviagiammarino/vqa-rad --max-answer-words 6

# Measure a scalar inside a struct answer column (here, each of StereoSet's candidate sentences)
inspect-dataset scan McGill-NLP/stereoset --config intersentence --split validation \
  --question-field context --answer-field sentences --answer-subfield sentence

# Compare each sample with its own subset (task mode detects the subset key itself)
inspect-dataset scan my-org/my-dataset --group-by subject

# Limit samples loaded
inspect-dataset scan flaviagiammarino/vqa-rad --limit 500

# Scan a local annotation directory (JSON samples + sidecar markdown gold),
# cross-checking gold against cached extraction-tool outputs
inspect-dataset scan path/to/samples/ \
  --files-root path/to/extraction-cache/ \
  --scanner-module my_benchmark.audit.scanners

# Run LLM-powered scanners (requires --model)
inspect-dataset scan flaviagiammarino/vqa-rad \
  --model openai/gpt-4o-mini --split test -o findings/

# Run only specific LLM scanners
inspect-dataset scan flaviagiammarino/vqa-rad \
  --model openai/gpt-4o-mini \
  --scanners label_correctness,ambiguity

# View a saved report
inspect-dataset report findings/

## Interactive viewer

`inspect-dataset view` serves a local React app for browsing findings and
triaging issues.

Like `inspect_ai` and `inspect-scout`, the built frontend artifacts are
shipped in the repository and included in the package.

### Getting started

1. Install development dependencies:

```bash
uv sync --extra dev
````

1. Return to the repository root and generate a findings directory if you do not already have one:

```bash
uv run inspect-dataset scan flaviagiammarino/vqa-rad --split test -o findings/
```

1. Launch the viewer:

```bash
uv run inspect-dataset view findings/
```

1. Open the URL printed by the command, usually:

```text
http://localhost:7576/
```

### Rebuilding the frontend

You only need to rebuild the frontend if you change files in `src/inspect_dataset/_view/www/`:

```bash
cd src/inspect_dataset/_view/www
npm install
npm run build
```

The viewer accepts either a single findings directory, a parent directory containing multiple findings directories, or an explicit list of directories:

```bash
uv run inspect-dataset view findings/
uv run inspect-dataset view results/
uv run inspect-dataset view results/vqa-rad/ results/medqa/
```

## Scanners

| Scanner                 | Severity    | What it flags                                                                                                                                        |
| ----------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `answer_length`         | medium      | Answers longer than N words (default: 4). Long answers are unlikely to be reproduced verbatim by exact-match scorers.                                |
| `duplicate_questions`   | high        | Questions that appear more than once. Duplicates inflate sample counts and bias metrics.                                                             |
| `inconsistent_format`   | low/medium  | Capitalisation, punctuation, or length deviations from the dataset majority (80%+ threshold).                                                        |
| `answer_distribution`   | high        | Datasets where a single answer accounts for ≥85% of samples — a model that always predicts that answer would score highly without any understanding. |
| `forced_choice_leakage` | medium      | Question sentences offering explicit options via "or" where the answer is one of those options. Samples with listed choices are skipped.             |
| `encoding_issues`       | low         | Questions or answers containing non-printable or control characters. Tabs inside fenced code and Asymptote `[asy]` blocks are ignored.               |
| `latex_escapes`         | medium      | LaTeX commands inside math whose backslash was eaten by a Python string escape, such as `\frac` stored as a form feed followed by `rac`.             |
| `mojibake`              | low/medium  | UTF-8 text decoded with the wrong codec (Windows-1252, Latin-1, Mac Roman), such as `‚Äì` for `–`. Checks choices too and gives the repair.          |
| `binary_question_ratio` | low         | Datasets where a high proportion of questions are binary (yes/no).                                                                                   |
| `markdown_integrity`    | low/medium  | Structural problems in Markdown answers: table column-count mismatches, missing delimiter rows, heading jumps, empty image links.                    |
| `extraction_artifacts`  | low/medium  | Characters betraying un-cleaned PDF/OCR extraction: ligatures, soft hyphens, zero-width characters, U+FFFD.                                          |
| `text_layer_recall`     | medium/high | With `--files-root`: gold words no extraction tool found on the page (typo candidates); for full-page gold, words every tool found that gold omits.  |
| `numeric_provenance`    | high        | With `--files-root`: numbers in the gold that no extraction tool extracted from the page — strong transcription-error candidates.                    |

### LLM Scanners (require `--model`)

| Scanner             | Severity | What it flags                                                                               |
| ------------------- | -------- | ------------------------------------------------------------------------------------------- |
| `ambiguity`         | medium   | Questions that are ambiguous or underspecified — can be interpreted multiple ways.          |
| `label_correctness` | high     | Samples where the ground-truth answer appears to be factually incorrect.                    |
| `answerability`     | medium   | Questions that cannot be answered from the provided context (auto-detects context columns). |

## Output

When `--output-dir` is given, findings are written as:

```text
findings/
    answer_length.json
    duplicate_questions.json
    inconsistent_format.json
    answer_distribution.json
    scan_summary.json    # counts by scanner/severity/category
    REPORT.md            # human-readable markdown
```

Each finding includes the scanner name, severity, category, explanation, sample index, sample ID (if available), and scanner-specific metadata.

`scan_summary.json` also has a `scanner_status` map with one entry per scanner that was run. A scanner that checked the dataset has `{"status": "ran"}`, whether or not it found anything. A scanner whose check does not fit the dataset has `{"status": "not_applicable", "reason": "..."}` and emits no findings. For example, `answer_length` and `inconsistent_format` measure answer text, so they do not apply to a list or struct answer column unless `--answer-subfield` selects a scalar inside it. The path is dotted, lists along it are measured element by element, and `*` measures each element of a list of strings. Plugin scanners can report the same status by raising `inspect_dataset.ScannerNotApplicable(reason)`.

Most scanners also skip a dataset that lacks the input they check. A dataset with an empty answer on every row, such as IFEval, gets `not_applicable` from the scanners that read answers. `image_mime_type` needs `--image-field`, and `text_layer_recall` and `numeric_provenance` need `--files-root`. `inspect-dataset scanners` lists what each built-in scanner requires. A plugin scanner declares the same with `requires`, and the runner then records `not_applicable` with a standard reason without calling it:

```python
from inspect_dataset import dataset_scanner


@dataset_scanner(description="Flag answers that repeat the question", requires=["answer"])
def answer_echoes_question(records, fields): ...
```

The names are `"answer"` (at least one row has a non-empty answer), `"image"` (an image field is set and at least one row has an image), and `"artifacts"` (at least one row has an extraction artifacts directory from `--files-root`). `ScannerDef` and `LLMScannerDef` take the same `requires` argument. An unknown name raises `ValueError`.

`scan_summary.json` also records how the population scanners (`inconsistent_format`, `answer_distribution` and `binary_question_ratio`) were grouped. On a benchmark made of subsets with different answer formats, one majority over the whole dataset is meaningless, and a balanced whole can hide one imbalanced subset. With a group field, these scanners compute their statistics per subset, and each finding names its group in `metadata.group` and in the explanation. Dataset-level findings become one per affected group. Groups with fewer than 20 answers are skipped by the two distribution scanners, where an imbalance is too likely to be chance. `group_by` is the field used, or `null`. `group_by_source` is `"option"` for `--group-by FIELD`, `"auto"` when task mode detected it, or `null` when there is no grouping or a Python caller did not pass `group_by_source` to `run_scanners`. Task mode groups automatically when exactly one of the `Sample.metadata` keys `dataset_name`, `subset`, `subject` or `category` has two or more values, for example `dataset_name` in BBH and `subject` in MMLU-Pro. `--no-group-by` turns that off. In Python, `load_inspect_task` sets `FieldMap.group` to the detected key, so set `fields.group = None` before `run_scanners` for pooled statistics. HuggingFace mode never groups automatically, because one config is already one subset.

`scan_summary.json` records the `split` and `config` that were scanned. For a HuggingFace dataset these are filled in when not given: the only split, or `train` when there are several, and the only config or the dataset's default one. `split_defaulted` and `config_defaulted` say whether each was filled in (`true`) or given (`false`). Both are `null` for task and local scans. When the dataset has several splits and none is `train`, or several configs and no default, the scan stops and lists the choices.

`scan_summary.json` records where the findings came from. `version` is the inspect-dataset version that ran the scan. When the dataset is an inspect_ai task, `task` is the task spec as given on the command line and `scorers` lists the registry names of the task's scorers, such as `["inspect_ai/choice"]`. A task with no scorer has `[]`, and scorers that are not inspect_ai registry objects are left out. Both are `null` for HuggingFace and local scans.

`scan_summary.json` records the `split` and `config` that were scanned. For a HuggingFace dataset these are filled in when not given: the only split, or `train` when there are several, and the only config or the dataset's default one. `split_defaulted` and `config_defaulted` say whether each was filled in (`true`) or given (`false`). Both are `null` for task and local scans. When the dataset has several splits and none is `train`, or several configs and no default, the scan stops and lists the choices.

## inspect_ai tasks

A task spec such as `inspect_evals/drop` loads the task's samples. Each record has `input` (the text of the last user message), `target` (the first target string), `targets` (every target string, as a list) and `id`, plus `choices` when the sample has them and every key of the sample's metadata. `input`, `target` and `id` are the question, answer and id fields. To measure every alternative answer of a list target, pass `--answer-field targets --answer-subfield '*'`.

## Integration with inspect-scout

inspect-scout tracks which samples models consistently fail or succeed on. inspect-dataset provides a complementary static pass before running evals. A future release will accept inspect-scout results directly to produce eval-informed findings and a `clean_ids.txt` export for quality-adjusted benchmark scores.

## Releasing

Releases publish to PyPI via [trusted publishing](https://docs.pypi.org/trusted-publishers/) — no API tokens. One-time setup: add a Trusted Publisher on PyPI for `Generality-Labs/inspect_dataset`, workflow `release.yml`, environment `pypi`.

```bash
uv version --bump minor      # or: patch / major — updates pyproject.toml
git commit -am "Release $(uv version --short)"
git tag "v$(uv version --short)"
git push origin main "v$(uv version --short)"
```

The tag push triggers `.github/workflows/release.yml`, which checks the tag against the package version, builds with `uv build`, and publishes.

## Development

```bash
uv sync --extra dev
uv run pytest
```

If you are working on the interactive viewer itself, also install frontend dependencies and build the bundle:

```bash
cd src/inspect_dataset/_view/www
npm install
npm run build
```
