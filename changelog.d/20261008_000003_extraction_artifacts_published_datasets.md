### Added

- `FieldMap.source_type`: where the records came from (`hf`, `inspect_task` or `local`). The scanner runner sets it, so a scanner can judge evidence by its source; it is `None` when a scanner is called directly.

### Changed

- `extraction_artifacts` no longer reports a non-breaking space on its own in a HuggingFace or task dataset, where web text is full of them; it is still counted beside another artifact, and still reported alone in local annotation files extracted from PDFs. A zero-width joiner or non-joiner between two letters of a non-Latin script is spelling (Bengali, Telugu, Persian), not an artifact. On a sweep of Inspect Evals these took the scanner from 2,103 findings to 366, mostly APPS, DROP, MMLU and MGSM.
