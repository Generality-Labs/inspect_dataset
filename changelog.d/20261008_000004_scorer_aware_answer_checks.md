### Changed

- `inconsistent_format` runs each check only when a scorer of the task is thrown by it. `exact` and `match` fold case and ignore punctuation, so under them capitalisation and trailing punctuation are no longer checked; `includes` folds case but compares punctuation; `pattern` compares everything. Length outliers are still checked under every verbatim scorer.
- `answer_length` and `inconsistent_format`'s length check no longer apply when the task also scores with `f1`, which gives partial credit for a long answer. This reverses the decision in #33 that `exact` beside `f1` runs the rules as before: on SQuAD, scored with both, they reported 1,495 findings, none of which could change a score. A scanner that does not apply says which aspects the task's scorers ignore.
