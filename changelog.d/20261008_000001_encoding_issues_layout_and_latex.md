### Changed

- `encoding_issues` no longer flags tabs used as layout: indentation (code pasted without a fence, such as tracebacks in issue text), a tab after a list bullet or number, and tabs separating the columns of a table row. A single tab inside prose is still flagged. On a sweep of Inspect Evals this removed nearly all of SWE-bench's and b3's findings.
- A control character that swallowed the start of a LaTeX command, such as a tab followed by `extsuperscript` (`\textsuperscript` with its backslash read as a string escape), is now medium severity, and the explanation and `latex_commands` metadata name the command. `latex_escapes` only looks inside math, so these were otherwise reported as stray tabs.
