# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `scanner_status` in `scan_summary.json`: `{"status": "ran"}` or `{"status": "not_applicable", "reason": ...}` for every scanner run, so a consumer can tell "checked and clean" from "did not apply". Not-applicable scanners are also listed in the terminal report and `REPORT.md`.
- `inspect_dataset.ScannerNotApplicable`, which a scanner raises to be recorded as not applicable.
- `--answer-subfield PATH` for `scan`: a dotted path to the scalar that `answer_length` and `inconsistent_format` measure inside a list or struct answer column. Lists along the path are measured element by element, and `*` measures each element of a list of strings. Findings made this way carry `answer_subfield` and `element_index` in their metadata.
- `mojibake` scanner: flags UTF-8 text decoded with the wrong codec (Windows-1252, Latin-1 or Mac Roman) in questions, answers and each choice. It reports a span only when re-encoding it with that codec and decoding as UTF-8 gives ordinary text, and it records the repair. It finds 15 fields in CoCoNot and 12 in MMLU-Pro ([#39](https://github.com/Generality-Labs/inspect_dataset/issues/39)).
- `split_defaulted` and `config_defaulted` in `scan_summary.json`. In HF mode they say whether the split and config were given or filled in. They are `null` for task and local scans ([#32](https://github.com/Generality-Labs/inspect_dataset/issues/32)).
- `inspect_dataset.loader.resolve_hf_split_config`, which fills in a missing split and config for a HF dataset ([#32](https://github.com/Generality-Labs/inspect_dataset/issues/32)).
- `latex_escapes` scanner for LaTeX commands whose backslash was eaten by a Python string escape. The typical case is `\frac` stored as a form feed followed by `rac`, which AIME 2024 has in two problems. It looks only inside math, checks the question, the answer and each choice, and reports the likely repair ([#38](https://github.com/Generality-Labs/inspect_dataset/issues/38)).
- `requires` on `ScannerDef`, `LLMScannerDef` and `@dataset_scanner`: the inputs a scanner needs (`"answer"`, `"image"`, `"artifacts"`). When one is missing, the runner records the scanner as not applicable with a standard reason and does not call it. `inspect-dataset scanners` shows each built-in's requirements ([#34](https://github.com/Generality-Labs/inspect_dataset/issues/34)).
- `--group-by FIELD` for `scan`: `inconsistent_format`, `answer_distribution` and `binary_question_ratio` compute their statistics per subset named by that field, instead of one majority over a whole benchmark of mixed subsets. Findings name their group in `metadata.group` and the explanation. Task mode picks the subset key from the sample metadata when there is one obvious candidate (`dataset_name`, `subset`, `subject` or `category`), and `--no-group-by` turns that off. `scan_summary.json` records `group_by` and `group_by_source` ([#36](https://github.com/Generality-Labs/inspect_dataset/issues/36)).

### Changed

- HF-mode scans pick the split and config when they are not given. `--split` now defaults to the dataset's only split, or to `train` when there are several. `--config` defaults to the only config or the dataset's default config. A dataset with several splits and no `train`, or several configs and no default, fails with a message that lists the choices and names the option to pass ([#32](https://github.com/Generality-Labs/inspect_dataset/issues/32)).
- Task-mode and local scans record `split` as `null` unless `--split` is given. Task-mode scans used to record the unused `--split` default, `train` ([#32](https://github.com/Generality-Labs/inspect_dataset/issues/32)).
- Task-mode scans of multi-subset tasks now group the population scanners by subset without being asked. On BBH, `inconsistent_format` falls from 1,420 findings to 1. Pass `--no-group-by` to get the pooled statistics back. In Python, `load_inspect_task` now sets `FieldMap.group` the same way, so `run_scanners` groups too. Set `fields.group = None` for pooled statistics ([#36](https://github.com/Generality-Labs/inspect_dataset/issues/36)).

### Fixed

- `answer_length` and `inconsistent_format` no longer measure the Python repr of list or struct answer columns, which flagged every row (all 2,123 rows of StereoSet's `sentences` column). On such a column they now emit no findings and are recorded as not applicable ([#26](https://github.com/Generality-Labs/inspect_dataset/issues/26)).
- `scan` loads HuggingFace datasets under owners that are also Python packages, such as `google/boolq` and `openai/gsm8k`, from the Hub. It used to treat them as inspect_ai task specs and fail with `No tasks found`. An `owner/name` spec is now a task only when the module `owner.name` exists or the inspect_ai registry has a task by that name. If the owner is a Python package and the Hub has no such dataset, `scan` says the spec is not an inspect_ai task either ([#31](https://github.com/Generality-Labs/inspect_dataset/issues/31)).
- `encoding_issues` no longer flags tabs inside fenced code blocks and Asymptote `[asy]` blocks, where they are indentation. This removes 9 of its 13 findings on MATH. The other 4 are tabs in prose. Other control characters in those blocks, and tabs outside them, are still flagged ([#38](https://github.com/Generality-Labs/inspect_dataset/issues/38)).
- `forced_choice_leakage` no longer misfires on prompt text, letter answers and empty answers. It reads options only from the words next to "or" in the last sentence that ends in a question mark, compares whole tokens, and skips empty answers and samples with listed choices. Over the inspect_evals tasks in the 2026-09-30 survey, findings fall from 3,672 to 1,609, and those left are real "A or B?" questions such as DROP comparisons ([#30](https://github.com/Generality-Labs/inspect_dataset/issues/30)).
- Scanners no longer report `ran` on a dataset that lacks their input. The answer scanners (including the LLM scanners) are not applicable when every answer is empty, as in IFEval, XSTest and CoCoNot. There, `forced_choice_leakage` had matched the empty answer against every question containing "or" (66 findings on IFEval, 38 on CoCoNot). `image_mime_type` is not applicable without an image field, and `text_layer_recall` and `numeric_provenance` without `--files-root` ([#34](https://github.com/Generality-Labs/inspect_dataset/issues/34)).
- Local scans apply `--image-field` on its own. It used to be ignored unless `--question-field`, `--answer-field` or `--id-field` was also given ([#34](https://github.com/Generality-Labs/inspect_dataset/issues/34)).

## [0.3.4] - 2026-04-04

### Added

- **Multi-dataset viewer**: `inspect-dataset view` now accepts multiple findings directories, a parent directory (auto-expanded), or an explicit list. A dataset picker home screen appears when more than one dataset is loaded; single-dataset mode redirects straight to findings (no breaking change).
- **`GET /api/datasets`** endpoint listing all loaded datasets with slug, name, sample count, and severity breakdown.
- All per-dataset API endpoints are now namespaced under `/api/{slug}/` (summary, findings, samples, sample, triage, export).
- **Dataset switcher** in the navbar header — a `<select>` dropdown appears when multiple datasets are loaded, letting you switch without returning to the home screen.
- **Auto-generated output directory**: `inspect-dataset scan` now always persists findings even when `--output-dir` is omitted, defaulting to `findings/<dataset-slug>_<YYYY-MM-DDTHH-MM-SS>`.

## [0.3.3] - 2026-04-04

### Added

- **Inline image rendering in the FindingDetail panel** — selecting a finding now shows the sample's question, answer, and any images directly in the right-hand panel. Images are loaded on demand from the original source; no bytes are re-serialised to disk.
  - HuggingFace datasets: image columns (stored as `{"bytes": ..., "path": ...}` dicts) are served straight from the HF cache via `GET /api/sample/{idx}`.
  - `inspect_ai` tasks: `Sample.files` bytes stored under `__files__` are served the same way.
  - MIME type detected from file extension (via `mimetypes`) or magic bytes (JPEG, PNG, GIF, WebP), returned as base64 data URLs.
  - Dataset is lazy-loaded on first image request and cached in the server process; subsequent requests are instant.
  - Graceful fallback for old findings dirs (no `source_type`) and for datasets that cannot be re-loaded: question/answer still shown, images omitted.
- **`source_type` and `revision` in `scan_summary.json`** — every scan now records `source_type` (`"hf"` or `"inspect_task"`) and the HF `revision` (or `null`). The view server uses these to re-open the original dataset for image serving.
- `GET /api/sample/{idx}` endpoint — returns `{index, question, answer, id, images, files}` for one record. `images` and `files` are lists of `{field/name, data_url}` objects.
- `SampleDetail`, `SampleImage`, `SampleFile` TypeScript interfaces.
- `fetchSampleDetail(idx)` API helper.

## [0.3.2] - 2026-04-04

### Added

- **Meaningful URLs** — the address bar now reflects UI state at all times:
  - `/findings` for the Findings tab; `/samples` for the Samples tab
  - `/` redirects to `/findings`
  - Active filters encoded as search params: `?scanner=answerability&severity=high&triage=pending`
  - Back/forward navigation restores the full filter state
- `react-router-dom` v7 added; tabs use `NavLink`, filters use `useSearchParams`, row navigation uses `useNavigate`
- Prev/Next buttons in the detail panel now disable at the list boundaries

### Changed

- Tab buttons replaced with `<a>` links (NavLink); test selector updated from `.nav-pills button` to `.nav-pills a`
- Filter state removed from Zustand store — owned entirely by the URL

## [0.3.1] - 2026-04-04

### Added

- **Samples tab shows question and answer content** — the Samples tab now displays Question and Answer columns (truncated with full-text tooltip), matching the HuggingFace dataset viewer style.
- `save_findings()` writes `samples.json` alongside scanner output when `records` and `fields` are provided; the view server loads it on startup.
- `Sample` TypeScript interface added to `types.ts`.
- `GET /api/samples` endpoint added to the view server.
- `fetchSamples()` added to the API client; degrades gracefully (returns `[]`) when `samples.json` is absent, so existing findings dirs still work.
- Test fixture extended with `samples.json`; `_create_fixture()` generates it.

## [0.3.0] - 2026-04-04

### Added

- **Interactive dataset explorer** (`inspect-dataset view <findings_dir>`):
  - aiohttp backend serving API endpoints and a single-page app.
  - Findings tab with scanner sidebar, severity/triage filters, and detail panel.
  - Samples tab with AG Grid table showing per-sample finding badges.
  - Triage actions (confirm/dismiss) with persistence to `triage.json`.
  - Keyboard shortcuts: `c` confirm, `d` dismiss, `n`/`p` next/prev finding.
  - `clean_ids.txt` export of sample IDs with no confirmed findings.
  - SPA-aware static serving with cache-busting headers (mirrors `inspect_ai` pattern).
- Frontend built with Vite, React, TypeScript, Bootstrap 5, AG Grid, Zustand.
- Playwright end-to-end tests for the view server (10 tests).
- `inspect-dataset tasks` command to list all registered `inspect_ai` tasks.
- `inspect-dataset scanners` command to list all registered scanners.
- `INSPECT_DATASET_MODEL` environment variable support for setting the default LLM model; `.env` files in cwd and home directory are loaded automatically.
- `aiohttp` added as a core dependency.
- `playwright` and `pytest-playwright` added to dev dependencies.

## [0.2.0] - 2026-04-03

### Added

- **LLM-powered scanners** enabled via `--model` (e.g. `--model openai/gpt-4o-mini`):
  - `ambiguity` — flags questions that are ambiguous or underspecified.
  - `label_correctness` — flags samples where the ground-truth answer appears incorrect.
  - `answerability` — flags questions unanswerable from the provided context (auto-detects context columns like `context`, `passage`, `paragraph`).
- Async scanner infrastructure: `LLMScannerDef`, `run_scanners_async()`.
- LLM helper module (`_llm.py`) with concurrent batch evaluation, semaphore-based rate limiting, and structured YES/NO judgment parsing via `inspect_ai` model API.
- `--model` CLI flag to enable LLM scanners.
- LLM scanner registry (`LLM_SCANNER_FACTORIES`) with CLI wiring.
- Tests for all three LLM scanners with mocked LLM calls.

## [0.1.2] - 2026-04-02

### Added

- `inspect_ai` Task/Dataset input support — scan `inspect_evals` tasks directly:
  - `inspect-dataset scan inspect_evals/gpqa` (package/task)
  - `inspect-dataset scan inspect_evals.gpqa@gpqa_diamond` (module@fn)
  - `inspect-dataset scan path/to/task.py@task_fn` (file@fn)
- `load_inspect_task()` and `load_task_from_spec()` in `loader.py` — converts `inspect.Sample` to internal `Record`/`FieldMap` format.
- Direct module import for `package/task` specs, bypassing the inspect_ai entry-point loader (avoids requiring all optional eval dependencies).
- Task spec vs HuggingFace slug detection via `importlib.util.find_spec`.
- `inspect_ai` added as optional dependency under `[inspect]` extras group.

## [0.1.1] - 2026-04-01

### Added

- `forced_choice_leakage` scanner — flags questions offering explicit options via "or" where the answer matches one of the options.
- `encoding_issues` scanner — flags non-printable or control characters in questions and answers.
- `binary_question_ratio` scanner — flags datasets where >50% of answers are yes/no.
- `--image-field` CLI option for multimodal duplicate detection.

### Changed

- `duplicate_questions` severity split: same question + same answer → HIGH; same question + different answers → LOW. With `--image-field`, uses (question, image) identity for grouping.

### Fixed

- `inconsistent_format`: false positive on answers ending with "etc.".

## [0.1.0] - 2026-03-31

### Added

- Initial release.
- HuggingFace dataset loader with field auto-detection.
- Four built-in scanners:
  - `answer_length` — flags answers longer than N words (default 4).
  - `duplicate_questions` — flags exact duplicate question text.
  - `inconsistent_format` — flags capitalisation, punctuation, and length outliers.
  - `answer_distribution` — flags class imbalance (≥85% single answer).
- Report generator: rich terminal output + REPORT.md.
- CLI: `inspect-dataset scan <dataset> [options]` with `--split`, `--revision`, `--question-field`, `--answer-field`, `--id-field`, `--scanners`, `--max-answer-words`, `--limit`, `-o/--output-dir`.
- JSON + Markdown output when `--output-dir` is given.
- Unit tests for all scanners.
