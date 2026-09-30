"""Joining task-mode samples to the raw dataset rows they came from (issue #53)."""

from __future__ import annotations

import json
from pathlib import Path

import datasets
from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset, Sample, csv_dataset, json_dataset

from inspect_dataset._source import SOURCE_FIELD, SourceInfo
from inspect_dataset.loader import load_inspect_task

ROWS = [
    {"qid": "q1", "question": "What is 2+2?", "answer": "4", "explanation": "Add them."},
    {"qid": "q2", "question": "What is 3+3?", "answer": "6", "explanation": "Double three."},
    {"qid": "q3", "question": "What is 5+5?", "answer": "10", "explanation": "Double five."},
]


def _to_sample(record: dict) -> Sample:
    # Like many evals: the explanation never reaches the sample, and the record is mutated
    record = dict(record)
    return Sample(input=record.pop("question"), target=record.pop("answer"))


def _jsonl(tmp_path: Path) -> Path:
    path = tmp_path / "rows.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    return path


def test_json_dataset_samples_carry_their_raw_row(tmp_path: Path):
    path = _jsonl(tmp_path)
    info = SourceInfo()
    records, _ = load_inspect_task(
        lambda: Task(dataset=json_dataset(str(path), _to_sample)), source_info=info
    )
    assert [r[SOURCE_FIELD] for r in records] == ROWS
    assert info.joined_by_record == 3
    assert info.joined_by_id == 0
    assert info.total == 3


def test_join_survives_shuffling(tmp_path: Path):
    path = _jsonl(tmp_path)
    records, _ = load_inspect_task(
        lambda: Task(dataset=json_dataset(str(path), _to_sample, shuffle=True, seed=3))
    )
    for record in records:
        assert record["input"] == record[SOURCE_FIELD]["question"]
        assert record["target"] == record[SOURCE_FIELD]["answer"]


def test_raw_row_is_captured_before_record_to_sample_mutates_it(tmp_path: Path):
    path = _jsonl(tmp_path)

    def destructive(record: dict) -> Sample:
        return Sample(input=record.pop("question"), target=record.pop("answer"))

    records, _ = load_inspect_task(lambda: Task(dataset=json_dataset(str(path), destructive)))
    assert records[0][SOURCE_FIELD]["question"] == "What is 2+2?"


def test_csv_dataset_is_joined(tmp_path: Path):
    path = tmp_path / "rows.csv"
    path.write_text(
        "qid,question,answer,explanation\n"
        + "".join(f"{r['qid']},{r['question']},{r['answer']},{r['explanation']}\n" for r in ROWS)
    )
    records, _ = load_inspect_task(lambda: Task(dataset=csv_dataset(str(path), _to_sample)))
    assert [r[SOURCE_FIELD]["explanation"] for r in records] == [r["explanation"] for r in ROWS]


def test_one_record_producing_several_samples_joins_each(tmp_path: Path):
    path = _jsonl(tmp_path)

    def two_per_record(record: dict) -> list[Sample]:
        return [
            Sample(input=record["question"], target=record["answer"]),
            Sample(input=record["question"] + " Explain.", target=record["explanation"]),
        ]

    records, _ = load_inspect_task(lambda: Task(dataset=json_dataset(str(path), two_per_record)))
    assert len(records) == 6
    assert all(r[SOURCE_FIELD]["qid"] == ROWS[i // 2]["qid"] for i, r in enumerate(records))


def test_limit_counts_only_the_records_kept(tmp_path: Path):
    path = _jsonl(tmp_path)
    info = SourceInfo()
    records, _ = load_inspect_task(
        lambda: Task(dataset=json_dataset(str(path), _to_sample)), limit=2, source_info=info
    )
    assert len(records) == 2
    assert (info.joined_by_record, info.total) == (2, 2)


def test_datasets_built_outside_a_capture_are_unaffected(tmp_path: Path):
    # The wrappers are installed once and must pass through when no capture is active
    path = _jsonl(tmp_path)
    load_inspect_task(lambda: Task(dataset=json_dataset(str(path), _to_sample)))
    dataset = json_dataset(str(path), _to_sample)
    assert [s.input for s in dataset] == [r["question"] for r in ROWS]


# ---------------------------------------------------------------------------
# Id join for samples built by hand from datasets.load_dataset
# ---------------------------------------------------------------------------


def _fake_load_dataset(tables: dict[str, list[dict]]):
    def load_dataset(path, name=None, split=None, **kwargs):
        return datasets.Dataset.from_list(tables[name or path])

    return load_dataset


def _hand_built_task(ids: list[str], configs: list[str]):
    def task() -> Task:
        samples = []
        for config in configs:
            for row in datasets.load_dataset("owner/ds", config, split="test"):
                samples.append(Sample(id=row["id"], input=row["question"], target="x"))
        wanted = set(ids)
        return Task(dataset=MemoryDataset([s for s in samples if s.id in wanted]))

    return task


def test_hand_built_samples_join_by_id_across_every_table(monkeypatch):
    tables = {
        "art": [{"id": "art_1", "question": "a?", "subject": "Art"}],
        "bio": [
            {"id": "bio_1", "question": "b?", "subject": "Bio"},
            {"id": "bio_2", "question": "c?", "subject": "Bio"},
        ],
    }
    monkeypatch.setattr(datasets, "load_dataset", _fake_load_dataset(tables))
    info = SourceInfo()
    records, _ = load_inspect_task(
        _hand_built_task(["art_1", "bio_2"], ["art", "bio"]), source_info=info
    )
    assert [r[SOURCE_FIELD]["subject"] for r in records] == ["Art", "Bio"]
    assert (info.joined_by_record, info.joined_by_id, info.id_column) == (0, 2, "id")
    assert info.loads == [
        {"path": "owner/ds", "name": "art", "split": "test"},
        {"path": "owner/ds", "name": "bio", "split": "test"},
    ]


def test_id_join_ignores_columns_with_repeated_values(monkeypatch):
    tables = {
        "only": [
            {"id": "s1", "question": "q", "group": "g"},
            {"id": "s2", "question": "q", "group": "g"},
        ]
    }
    monkeypatch.setattr(datasets, "load_dataset", _fake_load_dataset(tables))

    def task() -> Task:
        datasets.load_dataset("only", split="test")
        return Task(dataset=MemoryDataset([Sample(id="g", input="q", target="x")]))

    info = SourceInfo()
    records, _ = load_inspect_task(task, source_info=info)
    assert SOURCE_FIELD not in records[0]
    assert info.joined_by_id == 0
    assert info.id_column is None


def test_unmatched_samples_have_no_source_row(monkeypatch):
    tables = {"only": [{"id": "s1", "question": "q1"}]}
    monkeypatch.setattr(datasets, "load_dataset", _fake_load_dataset(tables))

    def task() -> Task:
        datasets.load_dataset("only", split="test")
        return Task(
            dataset=MemoryDataset(
                [Sample(id="s1", input="q1", target="x"), Sample(id="zz", input="?", target="x")]
            )
        )

    info = SourceInfo()
    records, _ = load_inspect_task(task, source_info=info)
    assert records[0][SOURCE_FIELD] == {"id": "s1", "question": "q1"}
    assert SOURCE_FIELD not in records[1]
    assert (info.joined_by_id, info.total) == (1, 2)


def test_summary_describes_the_join():
    info = SourceInfo(joined_by_record=3, joined_by_id=1, id_column="id", total=5)
    info.loads.append({"path": "owner/ds", "split": "test"})
    assert info.to_summary() == {
        "field": SOURCE_FIELD,
        "joined": 4,
        "total": 5,
        "joined_by_record": 3,
        "joined_by_id": 1,
        "id_column": "id",
        "loads": [{"path": "owner/ds", "split": "test"}],
    }
