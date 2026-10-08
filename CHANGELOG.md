# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- scriv-insert-here -->

## [0.6.0] - 2026-10-08

### Added

- `FieldMap.source_type`: where the records came from (`hf`, `inspect_task` or `local`). The scanner runner sets it, so a scanner can judge evidence by its source; it is `None` when a scanner is called directly.

### Changed

- `encoding_issues` no longer flags tabs used as layout: indentation (code pasted without a fence, such as tracebacks in issue text), a tab after a list bullet or number, and tabs separating the columns of a table row. A single tab inside prose is still flagged. On a sweep of Inspect Evals this removed nearly all of SWE-bench's and b3's findings.
- A control character that swallowed the start of a LaTeX command, such as a tab followed by `extsuperscript` (`\textsuperscript` with its backslash read as a string escape), is now medium severity, and the explanation and `latex_commands` metadata name the command. `latex_escapes` only looks inside math, so these were otherwise reported as stray tabs.
- `extraction_artifacts` no longer reports a non-breaking space on its own in a HuggingFace or task dataset, where web text is full of them; it is still counted beside another artifact, and still reported alone in local annotation files extracted from PDFs. A zero-width joiner or non-joiner between two letters of a non-Latin script is spelling (Bengali, Telugu, Persian), not an artifact. On a sweep of Inspect Evals these took the scanner from 2,103 findings to 366, mostly APPS, DROP, MMLU and MGSM.
- `inconsistent_format` runs each check only when a scorer of the task is thrown by it. `exact` and `match` fold case and ignore punctuation, so under them capitalisation and trailing punctuation are no longer checked; `includes` folds case but compares punctuation; `pattern` compares everything. Length outliers are still checked under every verbatim scorer.
- `answer_length` and `inconsistent_format`'s length check no longer apply when the task also scores with `f1`, which gives partial credit for a long answer. This reverses the decision in #33 that `exact` beside `f1` runs the rules as before: on SQuAD, scored with both, they reported 1,495 findings, none of which could change a score. A scanner that does not apply says which aspects the task's scorers ignore.

### Removed

- The `forced_choice_leakage` scanner. A question that offers its answer as one of two options ("Is it an MRI or a CT scan?") is an ordinary binary question: a model that pattern-matches still has to choose between the options. On a sweep of every Inspect Evals eval it reported 1,614 findings, 1,333 of them on DROP's reading-comprehension questions ("Which happened first, X or Y?", answered from a passage), and none worth acting on. `binary_question_ratio` still reports datasets dominated by binary questions. `--scanners forced_choice_leakage` is now an unknown scanner.

### Fixed

- `mojibake` no longer flags areas and volumes in ångströms. `Å²` and `Å³` are valid UTF-8 for `Ų` and `ų` when read as Windows-1252, so the scanner reported them as mojibake. They are now weak evidence, like a Mac Roman `√π`: reported only beside other mojibake in the same field, or between letters. On a sweep of Inspect Evals this removed 365 false positives from SciKnowEval and changed nothing else.
- The terminal report no longer crashes when a finding quotes sample text that looks like rich markup, such as MacBench's `[ANSWER]…[/ANSWER]`. Explanations and sample ids are escaped; before, the scan raised `MarkupError` after writing its findings and exited 1.

## [0.5.0] - 2026-10-03

The first release on PyPI. 0.4.0 was never published, so this section covers everything since 0.3.4. It covers:

- a dataset explorer in the viewer, with scanners you can run from it;
- local annotation directories, with markdown and cross-artifact scanners for auditing ground truth;
- scanners loaded from other modules with `--scanner-module`;
- many accuracy fixes for scans of real evaluation datasets.

### Added

- `image_mime_type` scanner: flags images whose declared MIME type, from a path's file extension or a data URI's header, does not match the image data, from its magic bytes. It catches images declared as JPEG that are really WebP or PNG, which some model APIs reject with HTTP 400. It reads HuggingFace image dicts, data URIs, raw bytes and base64. Raw bytes and plain base64 declare no type, so they are never flagged. It runs by default.
- Local annotation directories: `inspect-dataset scan path/to/samples/` loads a directory of JSON annotation files. Sidecar markdown is resolved through the `*_markdown_path` convention, and YAML frontmatter is stripped into `__frontmatter__` with the body offset recorded, so findings report real file line numbers ([#1](https://github.com/Generality-Labs/inspect_dataset/pull/1)).
- `Finding.line`: an optional 1-based line number that anchors a finding to a line of the gold file ([#1](https://github.com/Generality-Labs/inspect_dataset/pull/1)).
- `markdown_integrity` scanner: gold markdown that does not parse cleanly, such as table rows whose column count differs from the header, missing or malformed delimiter rows, empty table rows, heading-level jumps, and image links with empty targets ([#1](https://github.com/Generality-Labs/inspect_dataset/pull/1)).
- `extraction_artifacts` scanner: characters left by un-cleaned PDF or OCR extraction, such as ligatures, soft hyphens, zero-width characters, non-breaking spaces, a BOM and U+FFFD ([#1](https://github.com/Generality-Labs/inspect_dataset/pull/1)).
- `--scanner-module MODULE` (repeatable) imports scanners from another module: its module-level `SCANNERS` list, or else every `ScannerDef` attribute. A benchmark repo can ship its own domain-specific scanners this way, and their names work with `--scanners` ([#1](https://github.com/Generality-Labs/inspect_dataset/pull/1)).
- `--files-root DIR` resolves `DIR/<sample_id>/` for each record. Every non-empty `*.txt` or `*.md` file there, except `ground_truth.*` and `index.md`, is one extraction tool's text output ([#5](https://github.com/Generality-Labs/inspect_dataset/pull/5)).
- `text_layer_recall` scanner, which compares the gold against those tool outputs. A gold word that no tool found is a high-severity typo or hallucination candidate. For full-page gold (`task_type` contains "page"), a word every tool found but the gold lacks is a medium-severity omission ([#5](https://github.com/Generality-Labs/inspect_dataset/pull/5)).
- `numeric_provenance` scanner: every number in the gold, normalised for commas and `$`, must appear in at least one tool output. A miss is a high-severity transcription-error candidate ([#5](https://github.com/Generality-Labs/inspect_dataset/pull/5)).
- Audit view in the viewer: multi-line answers render as markdown, and an **Audit view** button opens a three-pane overlay of page image, rendered gold and raw source. Finding line anchors are highlighted in the raw pane, and a selector switches that pane between the gold markdown and each tool's cached output. `scan_summary.json` records `--files-root` so the viewer can find each sample's page image and tool outputs ([#5](https://github.com/Generality-Labs/inspect_dataset/pull/5)).
- Dataset explorer: `inspect-dataset view` with no findings directory opens a home screen listing cached HuggingFace datasets and installed inspect_ai tasks, plus a **Direct entry** tab for any other dataset or task. Any of them loads without a prior scan. Records show in a paginated AG Grid table with a detail sidebar that renders images, and the navbar links to the dataset's HuggingFace page. Datasets with several configs get a config selector ([#6](https://github.com/Generality-Labs/inspect_dataset/pull/6), [#7](https://github.com/Generality-Labs/inspect_dataset/pull/7)).
- Run scanners from the explorer: a **Scanners** panel lists the built-in scanners, with the static ones pre-selected and the LLM ones asking for a model. It runs them over the loaded records, shows findings with severity badges, and jumps to the record a finding is about. The server gains `GET /api/scanners` and `POST /api/explore/{session_id}/scan` ([#10](https://github.com/Generality-Labs/inspect_dataset/pull/10)).
- Explorer grid controls: the schema and record panels are resizable, columns can be shown or hidden from the schema panel ([#9](https://github.com/Generality-Labs/inspect_dataset/pull/9)), an **Expand nested** switch shows list and dict cells as JSON ([#13](https://github.com/Generality-Labs/inspect_dataset/pull/13)), and a **Multi-line** switch wraps long text and pretty-prints structured fields ([#16](https://github.com/Generality-Labs/inspect_dataset/pull/16)).
- `inspect-dataset view --reload` restarts the server when a Python file in the package changes. It needs the `watchfiles` package, which is not installed with inspect-dataset, and in-memory explorer sessions are lost on each restart ([#15](https://github.com/Generality-Labs/inspect_dataset/pull/15)).
- `--config NAME` for `scan` selects the config (subset) of a multi-config HuggingFace dataset. `scan_summary.json` records it as `config` ([#7](https://github.com/Generality-Labs/inspect_dataset/pull/7)).
- inspect-dataset is licensed under MIT. 0.3.4 shipped without a licence.
- Task scans join each sample to the raw dataset row it came from and keep it under `__source__`. Rows come from inspect_ai's `hf_dataset`, `csv_dataset` and `json_dataset` as the task builds, or, for samples built by hand, from a `datasets.load_dataset` table matched by sample id and checked against the sample's text. `source.<column>` in `--question-field`, `--answer-field`, `--id-field`, `--image-field` and `--group-by` names a column of that row. `scan_summary.json` gains a `source` key with the join counts and every `load_dataset` and `hf_dataset` call the task made, including its config, split and revision ([#53](https://github.com/Generality-Labs/inspect_dataset/issues/53)).
- `scanner_status` in `scan_summary.json`: `{"status": "ran"}` or `{"status": "not_applicable", "reason": ...}` for every scanner run, so a consumer can tell "checked and clean" from "did not apply". Not-applicable scanners are also listed in the terminal report and `REPORT.md`.
- `inspect_dataset.ScannerNotApplicable`, which a scanner raises to be recorded as not applicable.
- `--answer-subfield PATH` for `scan`: a dotted path to the scalar that `answer_length` and `inconsistent_format` measure inside a list or struct answer column. Lists along the path are measured element by element, and `*` measures each element of a list of strings. Findings made this way carry `answer_subfield` and `element_index` in their metadata.
- `mojibake` scanner: flags UTF-8 text decoded with the wrong codec (Windows-1252, Latin-1 or Mac Roman) in questions, answers and each choice. It reports a span only when re-encoding it with that codec and decoding as UTF-8 gives ordinary text, and it records the repair. It finds 15 fields in CoCoNot and 12 in MMLU-Pro ([#39](https://github.com/Generality-Labs/inspect_dataset/issues/39)).
- `split_defaulted` and `config_defaulted` in `scan_summary.json`. In HF mode they say whether the split and config were given or filled in. They are `null` for task and local scans ([#32](https://github.com/Generality-Labs/inspect_dataset/issues/32)).
- `inspect_dataset.loader.resolve_hf_split_config`, which fills in a missing split and config for a HF dataset ([#32](https://github.com/Generality-Labs/inspect_dataset/issues/32)).
- `latex_escapes` scanner for LaTeX commands whose backslash was eaten by a Python string escape. The typical case is `\frac` stored as a form feed followed by `rac`, which AIME 2024 has in two problems. It looks only inside math, checks the question, the answer and each choice, and reports the likely repair ([#38](https://github.com/Generality-Labs/inspect_dataset/issues/38)).
- `requires` on `ScannerDef`, `LLMScannerDef` and `@dataset_scanner`: the inputs a scanner needs (`"answer"`, `"image"`, `"artifacts"`). When one is missing, the runner records the scanner as not applicable with a standard reason and does not call it. `inspect-dataset scanners` shows each built-in's requirements ([#34](https://github.com/Generality-Labs/inspect_dataset/issues/34)).
- `--group-by FIELD` for `scan`: `inconsistent_format`, `answer_distribution` and `binary_question_ratio` compute their statistics per subset named by that field, instead of one majority over a whole benchmark of mixed subsets. Findings name their group in `metadata.group` and the explanation. Task mode picks the subset key from the sample metadata when there is one obvious candidate (`dataset_name`, `subset`, `subject` or `category`), and `--no-group-by` turns that off. `scan_summary.json` records `group_by` and `group_by_source` ([#36](https://github.com/Generality-Labs/inspect_dataset/issues/36)).
- `version`, `task` and `scorers` in `scan_summary.json`, so findings can be attributed to the inspect-dataset version that produced them and, in task mode, to the task spec and its scorer registry names. The version and scorers also appear in the terminal report and `REPORT.md`. Scanners can read the task's scorer names from `FieldMap.scorers` ([#40](https://github.com/Generality-Labs/inspect_dataset/issues/40)).
- `targets` in task-mode records: every target string of the sample, where `target` holds only the first. Pass `--answer-field targets --answer-subfield '*'` to measure every string of a list target, such as DROP's alternative answers or MBPP's test cases ([#37](https://github.com/Generality-Labs/inspect_dataset/issues/37)).
- `FieldMap.choices`: the column holding each sample's answer choices. Task mode sets it to `choices` when any sample has choices, so scanners can resolve a letter target such as `"B"` to the text of the choice it names ([#37](https://github.com/Generality-Labs/inspect_dataset/issues/37)).
- `duplicate_questions` and `image_mime_type` accept an image field that holds a list of images. `duplicate_questions` compares the whole list, and a missing image counts as a different image, so a question asked with and without an image is question reuse. `image_mime_type` checks each image and records its `image_index` in the finding ([#37](https://github.com/Generality-Labs/inspect_dataset/issues/37)).
- `images` in task-mode records: every image in the sample input, from all its messages. Task mode sets it as the image field when any sample has images, so `duplicate_questions` tells apart samples that share a question but not an image, and `image_mime_type` now runs on tasks. The viewer shows these images ([#37](https://github.com/Generality-Labs/inspect_dataset/issues/37)).

### Changed

- The built viewer frontend (`_view/www/dist`) ships in the package, so `inspect-dataset view` works from an install without building the frontend or installing Node.
- The viewer's home page lists findings directories passed to `inspect-dataset view <dir>` as cards, instead of opening a single one directly ([#7](https://github.com/Generality-Labs/inspect_dataset/pull/7)).
- Grid columns default to a width based on their content: at least the header's width, widening toward typical content length up to 600px, with the grid scrolling horizontally ([#9](https://github.com/Generality-Labs/inspect_dataset/pull/9), [#14](https://github.com/Generality-Labs/inspect_dataset/pull/14)).
- The Cached HF tab renders immediately from the local cache and fills in each dataset's metadata as it arrives, instead of waiting on the HuggingFace API for every cached dataset ([#12](https://github.com/Generality-Labs/inspect_dataset/pull/12)).
- `openai` is a core dependency, not only part of the `inspect` extra ([#6](https://github.com/Generality-Labs/inspect_dataset/pull/6)).
- Minimum dependency versions are raised: `datasets>=5.0.1` (was `>=2.0`), `rich>=15.0.0`, `aiohttp>=3.14.3`, `click>=8.4.2` and `openai>=2.53.0`, and in the `inspect` extra `inspect-ai>=0.3.252` ([#24](https://github.com/Generality-Labs/inspect_dataset/pull/24)).
- HF-mode scans pick the split and config when they are not given. `--split` now defaults to the dataset's only split, or to `train` when there are several. `--config` defaults to the only config or the dataset's default config. A dataset with several splits and no `train`, or several configs and no default, fails with a message that lists the choices and names the option to pass ([#32](https://github.com/Generality-Labs/inspect_dataset/issues/32)).
- Task-mode and local scans record `split` as `null` unless `--split` is given. Task-mode scans used to record the unused `--split` default, `train` ([#32](https://github.com/Generality-Labs/inspect_dataset/issues/32)).
- Task-mode scans of multi-subset tasks now group the population scanners by subset without being asked. On BBH, `inconsistent_format` falls from 1,420 findings to 1. Pass `--no-group-by` to get the pooled statistics back. In Python, `load_inspect_task` now sets `FieldMap.group` the same way, so `run_scanners` groups too. Set `fields.group = None` for pooled statistics ([#36](https://github.com/Generality-Labs/inspect_dataset/issues/36)).
- `answer_distribution` and `binary_question_ratio` measure a letter target as the text of the choice it names, so a multiple-choice task with the choices Yes and No is measured as yes and no rather than A and B. `answer_distribution` also checks the target letters for answer-position bias. Findings made this way carry `measured` (`"choice_text"` or `"letter"`) in their metadata. Output without choices is unchanged ([#33](https://github.com/Generality-Labs/inspect_dataset/issues/33)).
- `duplicate_questions` emits one finding per group of duplicates instead of one per row, so DROP's 569 groups no longer read as 1,423 problems. The finding sits on the group's first row. Its metadata lists every row in `duplicate_indices` and, new, `duplicate_ids`, and `duplicate_count` gives the group size. Exact duplicates now also carry `answers_agree`. Finding counts for this scanner drop accordingly. In the viewer, the Samples tab marks only the first row of a group, and confirming the finding drops only that row from the clean-id export, so a group of three or more still leaves copies in the export ([#35](https://github.com/Generality-Labs/inspect_dataset/issues/35)).
- Releases go through the **Prepare release** workflow, which bumps the version, collects the changelog and opens the release pull request; merging it tags the release and publishes to PyPI.

### Fixed

- Opening or reloading a viewer URL other than the root no longer returns 404. The server falls back to `index.html` for client-side routes, so deep links work.
- Loading a cached HuggingFace dataset in the explorer no longer fails with `AttributeError: 'str' object has no attribute 'get'` ([#7](https://github.com/Generality-Labs/inspect_dataset/pull/7)).
- `answer_length` and `inconsistent_format` no longer measure the Python repr of list or struct answer columns, which flagged every row (all 2,123 rows of StereoSet's `sentences` column). On such a column they now emit no findings and are recorded as not applicable ([#26](https://github.com/Generality-Labs/inspect_dataset/issues/26)).
- `scan` loads HuggingFace datasets under owners that are also Python packages, such as `google/boolq` and `openai/gsm8k`, from the Hub. It used to treat them as inspect_ai task specs and fail with `No tasks found`. An `owner/name` spec is now a task only when the module `owner.name` exists or the inspect_ai registry has a task by that name. If the owner is a Python package and the Hub has no such dataset, `scan` says the spec is not an inspect_ai task either ([#31](https://github.com/Generality-Labs/inspect_dataset/issues/31)).
- `encoding_issues` no longer flags tabs inside fenced code blocks and Asymptote `[asy]` blocks, where they are indentation. This removes 9 of its 13 findings on MATH. The other 4 are tabs in prose. Other control characters in those blocks, and tabs outside them, are still flagged ([#38](https://github.com/Generality-Labs/inspect_dataset/issues/38)).
- `forced_choice_leakage` no longer misfires on prompt text, letter answers and empty answers. It reads options only from the words next to "or" in the last sentence that ends in a question mark, compares whole tokens, and skips empty answers and samples with listed choices. Over the inspect_evals tasks in the 2026-09-30 survey, findings fall from 3,672 to 1,609, and those left are real "A or B?" questions such as DROP comparisons ([#30](https://github.com/Generality-Labs/inspect_dataset/issues/30)).
- Scanners no longer report `ran` on a dataset that lacks their input. The answer scanners (including the LLM scanners) are not applicable when every answer is empty, as in IFEval, XSTest and CoCoNot. There, `forced_choice_leakage` had matched the empty answer against every question containing "or" (66 findings on IFEval, 38 on CoCoNot). `image_mime_type` is not applicable without an image field, and `text_layer_recall` and `numeric_provenance` without `--files-root` ([#34](https://github.com/Generality-Labs/inspect_dataset/issues/34)).
- Local scans apply `--image-field` on its own. It used to be ignored unless `--question-field`, `--answer-field` or `--id-field` was also given ([#34](https://github.com/Generality-Labs/inspect_dataset/issues/34)).
- `samples.json` shows list and struct questions and answers as indented JSON rather than a Python repr, so the viewer shows them readably. Image bytes inside them appear as a byte count. Both fields are still strings ([#37](https://github.com/Generality-Labs/inspect_dataset/issues/37)).
- In task mode, `--question-field`, `--answer-field`, `--id-field` and `--image-field` now change only the roles they name, and the task's choices, images and scorers stay on the field map. Before, one override made the other roles auto-detected from the record columns, so a metadata `question` column could replace `input`, and `--image-field` on its own was ignored ([#37](https://github.com/Generality-Labs/inspect_dataset/issues/37)).
- In task mode, `answer_length` and `inconsistent_format` run only when the task scores with a scorer that compares answer text verbatim (`exact`, `match`, `includes` or `pattern`). Under other scorers they are recorded as not applicable with the scorer names as the reason. Before, `answer_length` flagged 93% of HumanEval's solution code, and `inconsistent_format` made 208 findings on MATH answers checked by expression equivalence ([#33](https://github.com/Generality-Labs/inspect_dataset/issues/33)).
- `duplicate_questions` identifies a sample by its question, its choices and the content of its images, through a sample identity shared by scanners that compare samples. Before, it compared the question text alone, so the 250 BBH hyperbaton rows, whose options are in `choices`, all looked like one question. The same image as a file and as a data URI now match. Answers are compared as the choice text a letter names, and list targets as the set of all targets. The finding text suggests `--image-field` only for an HF dataset with a column that looks like images, and names that column ([#35](https://github.com/Generality-Labs/inspect_dataset/issues/35)).
- `inspect_dataset.__version__` reported 0.2.0. It now reads the installed package's version, which `pyproject.toml` sets, so the two cannot drift again.

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
