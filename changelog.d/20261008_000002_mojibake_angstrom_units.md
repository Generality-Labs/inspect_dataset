### Fixed

- `mojibake` no longer flags areas and volumes in ångströms. `Å²` and `Å³` are valid UTF-8 for `Ų` and `ų` when read as Windows-1252, so the scanner reported them as mojibake. They are now weak evidence, like a Mac Roman `√π`: reported only beside other mojibake in the same field, or between letters. On a sweep of Inspect Evals this removed 365 false positives from SciKnowEval and changed nothing else.
