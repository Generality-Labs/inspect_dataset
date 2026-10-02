### Added

- Dataset explorer: `inspect-dataset view` with no findings directory opens a home screen listing cached HuggingFace datasets and installed inspect_ai tasks, and loads any of them without a prior scan. Records show in a paginated AG Grid table with a detail sidebar that renders images. Datasets with several configs get a config selector ([#6](https://github.com/Generality-Labs/inspect_dataset/pull/6), [#7](https://github.com/Generality-Labs/inspect_dataset/pull/7)).
- The explorer home lists findings directories passed to `inspect-dataset view <dir>` as cards, instead of jumping straight into a single one ([#7](https://github.com/Generality-Labs/inspect_dataset/pull/7)).
- Run scanners from the explorer: a **Scanners** panel lists the built-in scanners, with the static ones pre-selected and the LLM ones asking for a model. It runs them over the loaded records, shows findings with severity badges, and jumps to the record a finding is about. The server gains `GET /api/scanners` and `POST /api/explore/{session_id}/scan` ([#10](https://github.com/Generality-Labs/inspect_dataset/pull/10)).
- Explorer grid controls: columns size to fit their headers and scroll horizontally, the schema and record panels are resizable, columns can be shown or hidden from the schema panel ([#9](https://github.com/Generality-Labs/inspect_dataset/pull/9)), an **Expand nested** switch shows list and dict cells as JSON ([#13](https://github.com/Generality-Labs/inspect_dataset/pull/13)), and a **Multi-line** switch wraps long text and pretty-prints structured fields ([#16](https://github.com/Generality-Labs/inspect_dataset/pull/16)).
- `inspect-dataset view --reload` restarts the server when a Python file in the package changes. It needs `watchfiles`, from the dev dependency group, and in-memory explorer sessions are lost on each restart ([#15](https://github.com/Generality-Labs/inspect_dataset/pull/15)).

### Fixed

- Loading a cached HuggingFace dataset in the explorer no longer fails with `AttributeError: 'str' object has no attribute 'get'` ([#7](https://github.com/Generality-Labs/inspect_dataset/pull/7)).
