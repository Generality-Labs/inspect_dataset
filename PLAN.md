# inspect-dataset: Plan

A dataset quality scanner for AI evaluation datasets. Companion to
[inspect-scout](https://github.com/meridian-labs/inspect-scout), which scans
agent trajectories — inspect-dataset scans the underlying datasets themselves.

**Organisation:** Arcadia  
**Status:** v0.4.0 in progress

---

## Problem

When building evaluation benchmarks, verifying that every sample is valid is
slow and often done poorly. Common issues that slip through:

- Ground-truth answers that are too long to be reproduced verbatim by exact-match scorers
- Duplicate questions (inflated sample counts, biased metrics)
- Formatting inconsistencies in answers (case, punctuation, length outliers)
- Class imbalance (e.g. 90% "yes" in a yes/no benchmark)
- Answers leaked in the question text
- Questions that are unanswerable given the provided context

inspect-scout provides a complementary signal: samples that *all* models
consistently fail on are strong candidates for bad labels.

---

## Design

### Two modes

| Mode | Input | Use case |
| ---- | ----- | -------- |
| **Static** | Dataset (HuggingFace / CSV / JSON) | Pre-eval quality pass |
| **Eval-informed** | Dataset + inspect-scout parquet results | Post-eval deep audit |

v0.1 implements static mode only.

### Scanner interface

```python
# A scanner is a plain function: list of records → list of findings
def my_scanner(records: list[dict[str, Any]], fields: FieldMap) -> list[Finding]:
    ...
```

- `records`: raw dataset rows as dicts
- `fields`: resolved field mapping (question, answer, id fields)
- Returns zero or more `Finding` objects, one per flagged sample

Scanners are collected in a registry. The CLI runs all (or a named subset).

### Core types

```python
@dataclass
class Finding:
    scanner: str               # which scanner produced this
    severity: Severity         # "low" | "medium" | "high"
    category: Category         # "label_quality" | "question_quality" | "distribution" | "format" | "leakage"
    explanation: str
    sample_id: str | int | None
    sample_index: int
    metadata: dict[str, Any]   # scanner-specific extras (e.g. word count, duplicate_of)

@dataclass
class FieldMap:
    question: str   # field name for the question/prompt
    answer: str     # field name for the ground-truth answer
    id: str | None  # field name for the sample id (optional)
```

### Output (v0.1)

```text
<output-dir>/
    answer_length.json
    duplicate_questions.json
    inconsistent_format.json
    answer_distribution.json
    scan_summary.json       # counts by scanner/severity/category
    REPORT.md               # human-readable markdown
```

---

## Phased Roadmap

### v0.1 — Static scanners, CLI, JSON + markdown output ✓

### v0.1.1 — Scanner improvements from VQA-RAD audit ✓

Findings from auditing `flaviagiammarino/vqa-rad` (451 test samples) exposed three
gaps in the built-in scanners and one needed improvement:

- [x] **`duplicate_questions` severity split** — the scanner currently flags all
  duplicate questions as HIGH. In multimodal datasets, the same question is often
  asked about different images with different answers (valid). Split into:
  - Same question + same answer → HIGH (likely a real duplicate / copy-paste error)
  - Same question + different answers → LOW (informational; image context differentiates)
  This requires an `--image-field` option so the scanner can check whether the image
  also differs.
- [x] **`forced_choice_leakage` scanner** — flag questions that contain " or " where
  the answer is one of the explicitly offered options (e.g. *"is this an MRI or a CT
  scan?" → "mri"*). A model can exploit the question phrasing without visual
  understanding. Category: `leakage`, severity: `medium`.
- [x] **`encoding_issues` scanner** — flag questions or answers containing
  non-printable or non-ASCII characters (tabs, nulls, control characters, etc.).
  Found one real instance in VQA-RAD: `'skull \tcartilage and medulla'` (tab char).
  Category: `format`, severity: `low`.
- [x] **`binary_question_ratio` scanner** — flag datasets where a high proportion of
  questions are binary (yes/no answers), even if no single answer dominates above the
  85% imbalance threshold. VQA-RAD is 56% yes/no; a naive "always say no" strategy
  scores 29.5%. Complements `answer_distribution`. Category: `distribution`,
  severity: `low`.

### v0.1 — Tasks

- [x] Project scaffold (uv, pyproject.toml)
- [x] Core types: `Finding`, `FieldMap`, `Severity`, `Category`
- [x] Scanner runner: `run_scanners(records, fields, scanners) -> ScanRun`
- [x] Loaders: HuggingFace dataset, field auto-detection
- [x] Scanners:
  - [x] `answer_length` — answers above N words (exact-match proxy weakness)
  - [x] `duplicate_questions` — exact duplicate question text (known limitation: false positives on multimodal datasets where the same question is asked about different images — fix planned: `--image-field` option)
  - [x] `inconsistent_format` — case / punctuation / length outliers
  - [x] `answer_distribution` — class imbalance detection
- [x] Report generator: rich terminal output + REPORT.md
- [x] CLI: `inspect-dataset scan <dataset> [options]`
- [x] Tests: unit tests for each scanner
- [x] README

### v0.1.2 — inspect.Task / inspect.Dataset input ✓

`inspect_ai` Task objects (e.g. from `inspect_evals`) are now accepted as a
scan source alongside HuggingFace slugs. Four spec formats are supported:

```bash
inspect-dataset scan inspect_evals/gpqa_diamond      # package/task (recommended)
inspect-dataset scan inspect_evals.gpqa@gpqa_diamond # module@fn
inspect-dataset scan path/to/task.py@task_fn         # file@fn (via inspect_ai)
inspect-dataset scan flaviagiammarino/vqa-rad        # HF slug (unchanged)
```

`inspect.Sample` fields are mapped to the internal `Record`/`FieldMap` format:

| `inspect.Sample` field | maps to |
| ---------------------- | ------- |
| `input` (str or last user ChatMessage) | `question` |
| `target` (first element if list) | `answer` |
| `id` | sample id |
| `metadata` | merged into record |
| `files` | stored under `__files__` for view server |

The `package/task` path imports `package.task_name` directly and scans for
`@task`-decorated callables, bypassing the inspect_ai entry-point loader
(which requires all optional eval dependencies to be installed). Detection of
task specs vs HF slugs uses `importlib.util.find_spec` — if the left side of
`/` is an installed Python package, it's treated as a task spec.

- [x] `loader.py`: `load_inspect_task()`, `load_task_from_spec()` — converts
  `inspect.Sample` to `Record`; handles `str` input, `list[ChatMessage]`,
  `list[ContentBlock]`, and dict messages
- [x] `loader.py`: `files` preserved under `__files__` for view server
- [x] CLI: `find_spec`-based heuristic detects task specs vs HF slugs;
  `module@fn` and `package/task` both routed correctly
- [x] `scan_summary.json`: record source type and import path — `source_type`
  (`"hf"` | `"inspect_task"`) and `revision` written by `report.py:save_findings()`
- [x] View server: serve `__files__` bytes for inline rendering — `GET
  /api/sample/{idx}` lazy-loads the original dataset (HF cache or inspect task)
  and returns image bytes as base64 data URLs

### v0.2 — LLM scanners ✓

Three LLM-powered scanners that use `inspect_ai`'s model API. Enabled via
`--model` (e.g. `--model openai/gpt-4o-mini`). Without `--model`, only static
scanners run — existing behaviour is unchanged.

Architecture additions:

- `_llm.py`: model resolution via `inspect_ai.model.get_model()`, concurrent
  batch evaluation with semaphore-based rate limiting, structured YES/NO
  judgment parsing
- `LLMScannerDef`: async counterpart to `ScannerDef`; factory pattern
  (`_make_scanner(model_name)`) so the model is bound at CLI time
- `run_scanners_async()`: runs sync scanners sequentially then async scanners
  concurrently via `asyncio.gather`

Scanners:

- [x] `ambiguity` — LLM: "is this question ambiguous or underspecified?"
  Category: `question_quality`, severity: `medium`
- [x] `label_correctness` — LLM: "is this answer incorrect?"
  Category: `label_quality`, severity: `high`
- [x] `answerability` — LLM: "can this be answered from the provided context?"
  Auto-detects context columns (`context`, `passage`, `paragraph`, etc.).
  Category: `question_quality`, severity: `medium`
- [x] `--model` CLI flag
- [x] Async scanner runner (`run_scanners_async`)
- [x] LLM scanner registry (`LLM_SCANNER_FACTORIES`) + CLI wiring
- [x] Tests for all three scanners (mocked LLM calls)

### v0.3 — Interactive dataset explorer ✓

A local web UI for triaging findings — findings-first navigation rather than
data-first. The goal is to let a researcher work through flagged samples quickly,
dismiss false positives, and export a clean sample list.

#### Motivation

The HuggingFace dataset viewer lets you browse and SQL-query a dataset, but it
has no concept of quality findings. The `inspect-dataset report` command gives a
static summary. Neither lets you *triage*: step through each flagged sample,
look at the raw record, decide keep/dismiss, and track your decisions.

#### Existing infrastructure to leverage

The `inspect` log viewer (`@meridianlabs/log-viewer`, source at
`inspect_ai/src/inspect_ai/_view/www/`) uses the same pattern we'd follow:

- **Python backend**: aiohttp (or FastAPI) server, launched by a CLI command,
  opens a browser tab, serves a React SPA + REST API on localhost
- **Frontend stack**: React 19, Bootstrap 5, ag-grid for tables, Zustand for
  state, Vite build — all published as an npm library
- **Server pattern**: port-file management, kills stale servers, optional auth
  token for IDE integration

inspect-scout's `view` command wraps the same infrastructure for scout results.
We should follow the identical pattern so the three tools feel like a family.

The UI has two complementary modes, toggled by a top-level tab:

- **Findings view** — findings-first triage: work through every flagged sample,
  confirm or dismiss, export a clean list
- **Samples view** — dataset-first browsing: see every sample in a table with
  findings overlaid as badges; useful for spot-checking and exploring the raw data

#### Design

```bash
inspect-dataset view findings/
```

Launches a local webserver (default port 7576) and opens a browser.

**Findings tab — three-panel layout:**

```text
┌─────────────────────────────────────────────────────────────────┐
│  inspect-dataset  │  flaviagiammarino/vqa-rad  │  451 samples   │
│  [Findings ●]  [Samples]                                        │
│  83 findings  ·  0 dismissed  ·  0 confirmed                    │
├──────────────┬──────────────────────────────┬────────────────────┤
│  SCANNERS    │  FINDING                     │  SAMPLE            │
│              │                              │                    │
│ ● dup_q  37  │  [▲ MEDIUM]                 │  idx: 83           │
│ ● fcl    14  │  Same Q, diff images,        │  Q: is this an    │
│ ● ans_ln 20  │  same answer "no"            │     mri?          │
│ ● enc     2  │  indices: [83, 206]          │  A: no            │
│ ● dist    9  │                              │  image: [thumb]   │
│              │  ─────────────────────────── │                    │
│              │  [▲ MEDIUM]  ...             │  ──────────────── │
│              │  [▲ MEDIUM]  ...             │  [CONFIRM]        │
│              │                              │  [DISMISS]        │
│              │                              │  [SKIP]           │
└──────────────┴──────────────────────────────┴────────────────────┘
```

**Samples tab — dataset browser:**

```text
┌─────────────────────────────────────────────────────────────────┐
│  inspect-dataset  │  flaviagiammarino/vqa-rad  │  451 samples   │
│  [Findings]  [Samples ●]                                        │
│  Search: [________________]  Filter: [All ▼] [Any severity ▼]  │
├──────┬─────────────────────────────────┬──────────┬─────────────┤
│  idx │  question                       │  answer  │  findings   │
├──────┼─────────────────────────────────┼──────────┼─────────────┤
│    6 │  is the colon more prominent…   │  left    │  ▲ fcl      │
│   11 │  what structures are visible…   │  skull…  │  ● enc      │
│   83 │  is this an mri?                │  no      │  ▲ dup_q    │
│   86 │  is this an mri or a ct scan?   │  mri     │  ▲ fcl      │
│   … │  …                              │  …       │             │
└──────┴─────────────────────────────────┴──────────┴─────────────┘
                                                  [click row → detail panel]
```

ag-grid table, virtualised for large datasets. Findings column shows severity
badges; clicking a row opens the full sample detail in a side panel. Rows with
no findings are dimmed but visible — this is what makes it different from the
HF viewer: you see everything with findings overlaid.

**Key interactions:**

- Filter findings by scanner, severity, category, or triage status
- Click a finding → loads the sample record in the right panel
- For duplicate groups, show *all* members side-by-side
- Image fields rendered inline (HF `Image` feature / `inspect.Sample` files)
- Keyboard shortcuts: `c` confirm, `d` dismiss, `n/p` next/prev
- Decisions persisted to `findings/triage.json`

**REST API (aiohttp backend):**

| Endpoint | Description |
| -------- | ----------- |
| `GET /api/findings` | All findings from the output directory |
| `GET /api/summary` | Scanner/severity counts |
| `GET /api/sample/{idx}` | Raw record from the dataset |
| `POST /api/triage` | Save a confirm/dismiss decision |
| `GET /api/triage` | Current triage state |
| `GET /api/export` | Download `clean_ids.txt` |

The backend streams the dataset on demand (no full load into memory) by
re-opening the HF dataset with the same parameters recorded in
`scan_summary.json`.

#### Implementation tasks

- [x] `inspect-dataset view findings/` CLI command (click, mirrors inspect's
  `view start` pattern)
- [x] aiohttp server with the endpoints above; port-file management
- [x] React SPA (Vite, Bootstrap 5, ag-grid) — two-tab layout
- [x] Findings tab: finding list with filter/sort; sample detail panel
- [x] Samples tab: ag-grid table of all records with findings badges; side panel
- [x] Sample panel: renders question/answer/image fields inline in FindingDetail;
  handles both HF `Image` columns and `inspect.Sample` `files`; side-by-side
  for duplicate groups deferred
- [x] Triage actions (confirm/dismiss) persisted to `triage.json`
- [x] `clean_ids.txt` export — sample IDs with no confirmed findings
- [x] Keyboard shortcut layer (c/d/n/p)

#### Reuse opportunities

- Lift the aiohttp server scaffold directly from
  `inspect_ai/src/inspect_ai/_view/server.py` — port management, static file
  serving, browser-open logic
- Use the same Bootstrap 5 + ag-grid versions for visual consistency with the
  inspect family
- Consider whether the `@meridianlabs/log-viewer` library's `MetadataPanel` or
  `JsonPanel` components can be imported for the raw-record display rather than
  re-implementing them

### v0.3.2 — Meaningful URLs ✓

The SPA currently ignores URL entirely — tab switches don't update the address
bar and there is no way to share or deep-link to a particular view. Fix this so
the URL is always a faithful representation of UI state.

**Routing scheme:**

| URL | State |
| --- | ----- |
| `/` or `/findings` | Findings tab, no filters |
| `/findings?scanner=answer_length&severity=high&triage=pending` | Filtered |
| `/samples` | Samples tab |

The dataset is encoded in the server (one server = one findings dir), so it
does not need to appear in the path. If multi-dataset support is added
(v0.3.3), the dataset slug moves into the path (see below).

**Implementation notes:**

- Use React Router (`react-router-dom`) with `BrowserRouter`; the aiohttp
  `_WWWResource` already serves `index.html` for all non-API paths, so no
  server changes needed
- Zustand URL sync: on mount, read initial filter state from
  `useSearchParams`; on filter change, push to history with `useNavigate` /
  `URLSearchParams`
- Tab state maps to `/findings` vs `/samples` pathname
- Back/forward navigation should restore filter state

### v0.3.3 — Multi-dataset support ✓

Allow the viewer to serve and switch between several findings directories
without restarting the server. Useful when comparing scans of the same dataset
at different revisions, or scans of multiple related datasets in a session.

**Invocation:**

```bash
# Single dir — existing behaviour, unchanged
inspect-dataset view findings/

# Parent dir containing multiple findings dirs
inspect-dataset view results/

# Explicit list
inspect-dataset view results/vqa-rad/ results/medqa/ results/gpqa/
```

The server detects whether the argument(s) are individual findings dirs
(contain `scan_summary.json`) or parent dirs and expands them automatically.

**URL scheme (builds on v0.3.2):**

| URL | State |
| --- | ----- |
| `/` | Dataset picker (home screen) |
| `/<dataset-slug>/findings` | Findings tab for that dataset |
| `/<dataset-slug>/samples` | Samples tab for that dataset |

`<dataset-slug>` is derived from `scan_summary.json → dataset_name` (slashes
replaced with `--`, e.g. `flaviagiammarino--vqa-rad`).

**API changes:**

| Endpoint | Change |
| -------- | ------ |
| `GET /api/datasets` | New — list all datasets (name, slug, counts) |
| `GET /api/<slug>/summary` | Namespaced per dataset |
| `GET /api/<slug>/findings` | Namespaced per dataset |
| `GET /api/<slug>/samples` | Namespaced per dataset |
| `POST /api/<slug>/triage` | Namespaced per dataset |
| `GET /api/<slug>/export` | Namespaced per dataset |

**UI additions:**

- Home screen: card grid of available datasets with scanner/severity summary
- Dataset picker in the navbar header — dropdown to switch without going home
- Each dataset has its own `triage.json` (already the case for separate dirs)

### v0.3.4 — Auto-generated output directory ✓

When `--output-dir` is omitted, `scan` now creates a directory automatically so
results are always persisted without requiring an explicit flag.

**Default path:** `findings/<dataset-slug>_<YYYY-MM-DDTHH-MM-SS>` — e.g.
`findings/vqa-rad_2026-04-04T14-30-21`.

- [x] `cli.py`: derive default `output_dir` from dataset name + `datetime.now()`
  when `--output-dir` is not supplied; print the resolved path so the user
  knows where findings landed
- [x] Ensure `findings/` parent is created if it doesn't exist (already handled
  by `save_findings` → `output_dir.mkdir(parents=True, exist_ok=True)`)

### v0.4 — Dataset Explorer & Scanner Workbench (in progress)

The v0.3 UI was built as a findings viewer — it requires a pre-existing scan
output directory and is oriented around triaging findings. This phase reimagines
the UI as a **dataset explorer first**, with scan results as an overlay rather
than the entry point. The goal: a researcher should be able to open any dataset,
understand its structure, poke around in the data, and then selectively run
scanners — all without leaving the browser.

#### Motivation

The current UI has two blind spots:

1. **You need a scan before you can see anything.** If you just want to look at
   a dataset you've never seen before, you have to run the CLI first. The UI
   should be a zero-ceremony way to open and explore a dataset.
2. **Findings are disconnected from exploration.** Triaging a finding often
   requires context that the findings panel doesn't provide — column
   distributions, neighbouring samples, the dataset schema. Today you alt-tab
   to the HF viewer or a notebook for that context.

#### Core concepts

**Dataset sources — three ways in:**

| Source | How it works |
| ------ | ------------ |
| Cached HF datasets | List datasets already in the local HF cache (`~/.cache/huggingface/`); one click to load |
| Installed inspect tasks | Discover `@task`-decorated functions from installed packages (e.g. `inspect_evals`); run `record_to_sample` to materialise records |
| HF search / direct entry | Search bar in the UI header; enter a HF slug (e.g. `cais/hle`) or search by keyword; download + load on demand |

The home screen becomes a **dataset picker** rather than a findings-directory
picker — findings dirs are still loadable, but they're one source among several.

**Schema & statistics panel:**

Before diving into rows, show a dataset overview:

- Field names, types (string, int, float, image, list, dict), null counts
- Per-column summary statistics: unique values, min/max/mean for numerics,
  length distribution for strings, sample thumbnails for image columns
- Total row count, estimated memory footprint
- Dataset card / description (from HF metadata or README) if available

This gives a researcher the "shape" of the data in seconds, before they look at
a single row.

**Rich sample detail:**

The sample detail panel should render field values intelligently:

- **Images**: inline thumbnails, click to expand; support HF `Image` feature,
  base64 data URIs, and `inspect.Sample` files
- **Long text**: collapsible with syntax highlighting for markdown/code
- **JSON/dict fields**: interactive tree view (expand/collapse nodes)
- **Lists**: rendered as chips or expandable sub-tables
- **Nulls/missing**: visually distinct (greyed placeholder, not blank)

**Interactive table beyond basic browsing:**

- **Column-level filtering**: click a column header for type-appropriate filters
  (range slider for numerics, regex/substring for strings, has-image/no-image
  for image columns)
- **Sort by any column**, including derived columns like answer length or
  finding count
- **Column visibility**: hide/show columns; useful for wide datasets with
  dozens of metadata fields
- **Row selection**: select rows to form an ad-hoc subset for export or
  scanner targeting
- **Full-text search**: search across all string fields simultaneously

#### Scanner workbench

Scanners should be runnable from the UI, not just the CLI:

- **Scanner panel**: list of available scanners (builtin + LLM) with
  descriptions; toggle which to run; configure parameters (e.g.
  `max_answer_words`)
- **Run scope**: option to run on the full dataset or only the currently
  filtered/selected rows — useful for re-checking a subset after changes or
  for expensive LLM scanners where you don't want to scan 3,000 samples
- **Live results**: findings appear incrementally as scanners complete;
  the findings overlay on the table updates in real time
- **Re-scan**: after dismissing findings and adjusting filters, re-run
  scanners without restarting
- **Model selector**: for LLM scanners, pick a model from a dropdown
  (populated from available API keys / inspect_ai model registry)

The existing findings-first triage workflow (confirm/dismiss/skip) remains
available as a view mode, but it's no longer the only way in.

#### Dataset provenance & source code

For inspect tasks, the UI should surface how the dataset was constructed:

- **Source function**: show the module path and link to the source code of the
  `record_to_sample` / dataset-loading function (e.g.
  `inspect_evals/core_bench/dataset.py:read_core_bench_dataset`). Rendered as
  a syntax-highlighted read-only code block.
- **Data pipeline**: where the raw data lives on disk (HF cache path, or
  custom cache like `/Users/matt/Library/Caches/inspect_evals/CORE-Bench/data/`)
- **Upstream dataset card**: link to the HF dataset page or paper

Some evals have complex data pipelines — e.g. CORE-Bench downloads an encrypted
JSON from HF, decrypts it with GPG, then uses capsule DOIs to download tarballs
containing code, results, notebooks, and images per sample. Enabling full
exploration of these nested artefacts (browsing files inside a capsule tarball)
is aspirational — not for this phase — but surfacing the provenance info and
source code is achievable and valuable.

#### Additional suggestions

**Comparative / side-by-side view:**

For duplicate findings, show all members of the duplicate group side by side
rather than one at a time. Extend this to a general "compare N samples" mode
where you can pin samples and see them in columns. Useful for spotting patterns
in clusters of similar findings.

**Annotation & notes:**

Extend triage beyond binary confirm/dismiss. Allow free-text notes on any
sample (not just flagged ones). Notes persist to a `annotations.json` alongside
triage decisions. This turns the UI into a lightweight annotation tool for
dataset curation — researchers can flag samples they notice during exploration
even if no scanner caught them.

**Image gallery view:**

For multimodal datasets, offer a grid/gallery layout that shows image
thumbnails with minimal text overlay (sample ID, answer, finding badges).
Faster for visual scanning than a row-based table. Click a thumbnail to open
the full sample detail.

**Column-level quality heatmap:**

A bird's-eye visualisation: one row per scanner, one column per dataset column,
cells coloured by finding density. Immediately shows which fields have the most
issues. Clickable — zoom into that scanner×field combination.

**Export options:**

- Filtered subset as CSV/JSON/Parquet
- `clean_ids.txt` (existing) — IDs with no confirmed findings
- `flagged_ids.txt` — IDs with confirmed findings
- HuggingFace correction — submit a corrective PR to a HF dataset
- HuggingFace dataset push — upload a cleaned subset back to HF (stretch goal)

**Shareable reports:**

Generate a static HTML report from the current view state (filters, triage
decisions, annotations) that can be shared with collaborators who don't have
the tool installed. Similar to how inspect's log viewer can export a standalone
HTML file.

#### Implementation sketch

This is a significant expansion of the UI. Rough phasing:

1. **v0.4.0 — Dataset picker + direct loading** ✓: home screen lists cached HF
   datasets and installed inspect tasks; direct entry tab; load without prior
   scan; HF API split detection; explorer session management; AG Grid data
   table with paginated records; record detail sidebar with image rendering;
   HuggingFace link in navbar; visible placeholders for null/empty values
2. **v0.4.1 — Schema panel + rich rendering**: dataset overview statistics;
   intelligent field rendering in sample detail
3. **v0.4.2 — Scanner workbench**: run scanners from UI; scope to
   filtered/selected rows; live results
4. **v0.4.3 — Annotations, gallery view, comparative view**: extended
   interaction modes
5. **v0.4.4 — Export + shareable reports**: static HTML export, filtered
   subset download

### User Stories (backlog)

Quick-fire ideas to pick up as time allows — not yet assigned to a version.

- [ ] AAU, when I view a dataset grid, I can easily switch between each row being a single line with truncated text to each row being tall enough to show its full text (within a reasonable limit)
- [ ] AAU, when I view the explorer, I can change between dark and light themes
- [ ] AAU, when I click on an image thumbnail in the record sidebar, I see the image in a lightbox
- [ ] AAU, when I go to the homepage, the list of cached HF datasets should load within 1 second
- [ ] AAU, when I view a dataset grid, I can see which split I'm viewing and easily switch between available splits
- [ ] AAU, when I go to the homepage, the list of datasets take up available vertical space
- [ ] AAU, when I view a dataset grid that includes references images, the images should be shown in the record sidebar. Example: inspect_evals/zerobench, `question_images: ["images/74_0.png"]`
- [ ] AAU, when I view a HF dataset grid, the schema view should include the raw json of the schema for debugging purposes
- [ ] AAU, when I view a HF dataset grid, the record sidebar should include the type of each field from the schema

### v0.5 — Eval-informed scanners (inspect-scout integration, planned)

- [ ] `universal_failure` — all models fail → bad label candidate
- [ ] `universal_success` — all models succeed → leakage candidate
- [ ] `high_variance` — models disagree sharply → ambiguity candidate
- [ ] `model_contradicts_label` — model answer matches label but scorer gave 0
- [ ] `--scout-results` CLI flag accepts inspect-scout parquet directory

---

## CLI Design

```bash
# Scan a HuggingFace dataset
inspect-dataset scan flaviagiammarino/vqa-rad \
  --split test \
  --answer-field answer \
  --question-field question \
  -o findings/

# Scan an inspect_ai Task — package/task (recommended)
inspect-dataset scan inspect_evals/gpqa_diamond -o findings/

# Or with explicit module@fn syntax
inspect-dataset scan inspect_evals.gpqa@gpqa_diamond -o findings/

# Limit to specific scanners
inspect-dataset scan ... --scanners answer_length,duplicate_questions

# Custom max answer words threshold
inspect-dataset scan ... --max-answer-words 6

# View report from saved findings
inspect-dataset report findings/

# Interactive dataset explorer (v0.3)
inspect-dataset view findings/

# (v0.4) Enrich with inspect-scout results
inspect-dataset scan ... --scout-results scout_results/
```

---

## Integration with inspect-scout

```text
Dataset ──► inspect-dataset (static) ──► findings/
                                              │
Eval run ──► inspect-scout ──► scout_results/─┘
                                              │
                                    inspect-dataset (eval-informed)
                                              │
                                    REPORT.md + clean_ids.txt
```

The `clean_ids.txt` output feeds back into eval workflows — re-run the eval
filtered to clean samples only for a quality-adjusted benchmark score.

---

## Directory Structure (target)

```text
inspect-dataset/
    src/inspect_dataset/
        __init__.py
        _types.py           # Finding, FieldMap, Severity, Category
        scanner.py          # run_scanners(), ScanRun
        loader.py           # HF + CSV/JSON loading, field auto-detection
        report.py           # terminal + markdown report generation
        cli.py              # click CLI entry point
        scanners/
            __init__.py     # BUILTIN_SCANNERS registry
            answer_length.py
            duplicate_questions.py
            inconsistent_format.py
            answer_distribution.py
    tests/
        test_answer_length.py
        test_duplicate_questions.py
        test_inconsistent_format.py
        test_answer_distribution.py
    PLAN.md
    README.md
    pyproject.toml
```
