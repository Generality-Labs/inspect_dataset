---
name: inspect-dataset-audit
description: Audit a HuggingFace dataset for quality issues using the inspect-dataset tool. Use this skill whenever the user wants to scan, audit, investigate, or find problems in a dataset — especially HuggingFace datasets used for AI evaluation benchmarks. Triggers on phrases like "audit this dataset", "scan for issues", "check data quality", "what's wrong with this dataset", "find problems in", "investigate the dataset". Also use when the user asks to write a new scanner for inspect-dataset or extend its built-in checks.
---

# inspect-dataset audit

You are auditing a dataset for quality issues using the `inspect-dataset` tool at `/Users/matt/Developer/inspect_ai/inspect-dataset`. Always use `uv run` from that directory to invoke the CLI.

## Step 1: Run the built-in scanners

Run a scan against the target dataset. If the user hasn't specified a split, start with `test`; fall back to `train` if test doesn't exist.

```bash
cd /Users/matt/Developer/inspect_ai/inspect-dataset
uv run inspect-dataset scan <dataset> --split <split> --limit 200 -o /tmp/inspect-dataset-audit/
```

Use `--limit 200` as a default unless the user specifies otherwise — enough to get representative signal without being slow.

Read the output from the terminal and the saved files:

- `/tmp/inspect-dataset-audit/scan_summary.json` — counts by scanner/severity
- `/tmp/inspect-dataset-audit/REPORT.md` — human-readable summary
- Individual JSON files per scanner for detailed findings

## Step 2: Explore findings in context

Don't just report raw scanner output. Load a sample of the flagged records and look at them directly to understand what's actually going on. Use the HuggingFace `datasets` library:

```python
from datasets import load_dataset
ds = load_dataset("<dataset>", split="<split>")
# Look at specific flagged indices
for idx in [<flagged indices>]:
    print(ds[idx])
```

For each scanner that produced findings, answer:

- Are these real problems or false positives?
- What does the underlying data actually look like?
- What would the impact be on an evaluation using this dataset?

## Step 3: Identify gaps in the built-in scanners

After reviewing the data directly, think about what the built-in scanners missed. The four built-in scanners check:

- Answer length (too long for exact-match)
- Duplicate questions
- Capitalisation/punctuation/length inconsistency
- Answer class imbalance

Common issues they don't catch:

- Answers that appear verbatim in the question (leakage)
- Multiple valid answers for the same question
- Questions that reference external context not in the record (e.g. "what is shown in the image above?")
- Answers that are nonsensical or clearly wrong
- Language or encoding issues (odd characters, mixed scripts)
- Dataset-specific structural issues

Look for these patterns in the sample you loaded. Note anything unusual.

## Step 4: Propose (and optionally implement) new scanners

If you spotted a pattern worth scanning for systematically, propose a new scanner. A scanner is a plain Python function:

```python
from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id

def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings = []
    for i, record in enumerate(records):
        answer = str(record.get(fields.answer, "") or "").strip()
        question = str(record.get(fields.question, "") or "").strip()
        # ... your check ...
        if <condition>:
            findings.append(Finding(
                scanner="my_scanner_name",
                severity="low",  # "low" | "medium" | "high"
                category="label_quality",  # "label_quality" | "question_quality" | "distribution" | "format" | "leakage"
                explanation="...",
                sample_index=i,
                sample_id=get_sample_id(record, fields, i),
                metadata={},
            ))
    return findings

my_scanner = ScannerDef(name="my_scanner_name", fn=_scan, description="...")
```

Save new scanners to `src/inspect_dataset/scanners/<name>.py` and register them in `src/inspect_dataset/scanners/__init__.py`.

Ask the user before writing files — describe what the scanner would check and why, then implement if they want it.

## Step 5: Summarise

Give the user a clear summary:

1. **Dataset overview**: name, split, sample count, field names detected
2. **Built-in scanner findings**: table of issues found, with severity and count
3. **Contextual assessment**: which findings are real vs. likely false positives, and why
4. **Gaps identified**: patterns noticed that aren't covered by existing scanners
5. **Recommended actions**: concrete next steps (remove duplicates, fix label X, add scanner for Y)

Keep the summary actionable — the goal is to help the user decide whether this dataset is ready for evaluation use, and what to fix if not.
