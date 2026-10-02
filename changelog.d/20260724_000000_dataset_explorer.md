### Added

- Dataset explorer: `inspect-dataset view` with no findings directory opens a home screen listing cached HuggingFace datasets and installed inspect_ai tasks, plus a **Direct entry** tab for any other dataset or task. Any of them loads without a prior scan. Records show in a paginated AG Grid table with a detail sidebar that renders images, and the navbar links to the dataset's HuggingFace page. Datasets with several configs get a config selector ([#6](https://github.com/Generality-Labs/inspect_dataset/pull/6), [#7](https://github.com/Generality-Labs/inspect_dataset/pull/7)).
- Run scanners from the explorer: a **Scanners** panel lists the built-in scanners, with the static ones pre-selected and the LLM ones asking for a model. It runs them over the loaded records, shows findings with severity badges, and jumps to the record a finding is about. The server gains `GET /api/scanners` and `POST /api/explore/{session_id}/scan` ([#10](https://github.com/Generality-Labs/inspect_dataset/pull/10)).
- Explorer grid controls: the schema and record panels are resizable, columns can be shown or hidden from the schema panel ([#9](https://github.com/Generality-Labs/inspect_dataset/pull/9)), an **Expand nested** switch shows list and dict cells as JSON ([#13](https://github.com/Generality-Labs/inspect_dataset/pull/13)), and a **Multi-line** switch wraps long text and pretty-prints structured fields ([#16](https://github.com/Generality-Labs/inspect_dataset/pull/16)).
- `inspect-dataset view --reload` restarts the server when a Python file in the package changes. It needs the `watchfiles` package, which is not installed with inspect-dataset, and in-memory explorer sessions are lost on each restart ([#15](https://github.com/Generality-Labs/inspect_dataset/pull/15)).

### Changed

- The viewer's home page lists findings directories passed to `inspect-dataset view <dir>` as cards, instead of opening a single one directly ([#7](https://github.com/Generality-Labs/inspect_dataset/pull/7)).
- Grid columns default to a width based on their content: at least the header's width, widening toward typical content length up to 600px, with the grid scrolling horizontally ([#9](https://github.com/Generality-Labs/inspect_dataset/pull/9), [#14](https://github.com/Generality-Labs/inspect_dataset/pull/14)).
- The Cached HF tab renders immediately from the local cache and fills in each dataset's metadata as it arrives, instead of waiting on the HuggingFace API for every cached dataset ([#12](https://github.com/Generality-Labs/inspect_dataset/pull/12)).

### Fixed

- Loading a cached HuggingFace dataset in the explorer no longer fails with `AttributeError: 'str' object has no attribute 'get'` ([#7](https://github.com/Generality-Labs/inspect_dataset/pull/7)).
