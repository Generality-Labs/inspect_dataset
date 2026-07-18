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
| `forced_choice_leakage` | medium      | Questions offering explicit options via "or" where the answer is one of those options.                                                               |
| `encoding_issues`       | low         | Questions or answers containing non-printable or control characters.                                                                                 |
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

## Integration with inspect-scout

inspect-scout tracks which samples models consistently fail or succeed on. inspect-dataset provides a complementary static pass before running evals. A future release will accept inspect-scout results directly to produce eval-informed findings and a `clean_ids.txt` export for quality-adjusted benchmark scores.

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
