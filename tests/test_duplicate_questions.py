from inspect_dataset._types import FieldMap
from inspect_dataset.scanners.duplicate_questions import duplicate_questions

FIELDS = FieldMap(question="q", answer="a")


def recs(*pairs: tuple[str, str]) -> list[dict]:
    """Build records from (question, answer) pairs."""
    return [{"q": q, "a": a} for q, a in pairs]


# ---------------------------------------------------------------------------
# No image field — classify by answer agreement
# ---------------------------------------------------------------------------


def test_no_duplicates_no_findings():
    data = recs(("what is A?", "yes"), ("what is B?", "no"), ("what is C?", "yes"))
    assert duplicate_questions(data, FIELDS) == []


def test_no_image_same_answer_is_high():
    data = recs(("is it broken?", "no"), ("other q", "yes"), ("is it broken?", "no"))
    findings = duplicate_questions(data, FIELDS)
    assert len(findings) == 2
    assert all(f.severity == "high" for f in findings)
    assert all(f.metadata["answers_agree"] is True for f in findings)


def test_no_image_different_answer_is_low():
    data = recs(
        ("is the heart enlarged?", "yes"), ("other", "no"), ("is the heart enlarged?", "no")
    )
    findings = duplicate_questions(data, FIELDS)
    assert len(findings) == 2
    assert all(f.severity == "low" for f in findings)
    assert all(f.metadata["answers_agree"] is False for f in findings)


def test_no_image_triplicate_same_answer_is_high():
    data = recs(("same?", "yes"), ("same?", "yes"), ("same?", "yes"))
    findings = duplicate_questions(data, FIELDS)
    assert len(findings) == 3
    assert all(f.severity == "high" for f in findings)


# ---------------------------------------------------------------------------
# With image field — three-way classification
# ---------------------------------------------------------------------------

IMG_FIELDS = FieldMap(question="q", answer="a", image="img")

IMG1 = {"bytes": b"image-one", "path": None}
IMG2 = {"bytes": b"image-two", "path": None}
IMG3 = {"bytes": b"image-three", "path": None}


def img_rec(question: str, answer: str, img: dict) -> dict:
    return {"q": question, "a": answer, "img": img}


def test_exact_duplicate_same_image_is_high():
    # Same question, same image → real duplicate
    data = [img_rec("is this normal?", "no", IMG1), img_rec("is this normal?", "no", IMG1)]
    findings = duplicate_questions(data, IMG_FIELDS)
    high = [f for f in findings if f.severity == "high"]
    assert len(high) == 2
    assert all(f.metadata["duplicate_type"] == "exact" for f in high)


def test_same_question_different_image_same_answer_is_medium():
    # Same question, different images, same answer → image-independent question
    data = [img_rec("is this an mri?", "no", IMG1), img_rec("is this an mri?", "no", IMG2)]
    findings = duplicate_questions(data, IMG_FIELDS)
    reuse = [f for f in findings if f.metadata.get("duplicate_type") == "question_reuse"]
    assert len(reuse) == 2
    assert all(f.severity == "medium" for f in reuse)
    assert all(f.metadata["answers_agree"] is True for f in reuse)


def test_same_question_different_image_different_answer_is_low():
    # Same question, different images, different answers → standard VQA reuse
    data = [
        img_rec("is the heart enlarged?", "yes", IMG1),
        img_rec("is the heart enlarged?", "no", IMG2),
    ]
    findings = duplicate_questions(data, IMG_FIELDS)
    reuse = [f for f in findings if f.metadata.get("duplicate_type") == "question_reuse"]
    assert len(reuse) == 2
    assert all(f.severity == "low" for f in reuse)
    assert all(f.metadata["answers_agree"] is False for f in reuse)


def test_mixed_exact_and_reuse_findings():
    # idx 0 and 1: same question + same image (exact duplicate, HIGH)
    # idx 2: same question + different image, different answer (VQA reuse, LOW)
    data = [
        img_rec("what is shown?", "brain", IMG1),
        img_rec("what is shown?", "brain", IMG1),
        img_rec("what is shown?", "heart", IMG2),
    ]
    findings = duplicate_questions(data, IMG_FIELDS)
    exact = [f for f in findings if f.metadata.get("duplicate_type") == "exact"]
    reuse = [f for f in findings if f.metadata.get("duplicate_type") == "question_reuse"]
    assert len(exact) == 2
    assert all(f.severity == "high" for f in exact)
    assert len(reuse) == 3
    assert all(f.severity == "low" for f in reuse)


def test_no_duplicates_with_image_no_findings():
    data = [
        img_rec("is this normal?", "yes", IMG1),
        img_rec("is the heart enlarged?", "no", IMG2),
    ]
    assert duplicate_questions(data, IMG_FIELDS) == []


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def test_case_insensitive_normalisation():
    data = recs(("What Is A?", "yes"), ("what is a?", "yes"))
    findings = duplicate_questions(data, FIELDS)
    assert len(findings) == 2


def test_whitespace_normalisation():
    data = recs(("  what is a?  ", "yes"), ("what is a?", "yes"))
    findings = duplicate_questions(data, FIELDS)
    assert len(findings) == 2


# ---------------------------------------------------------------------------
# Indices and IDs
# ---------------------------------------------------------------------------


def test_finding_indices_are_correct():
    data = recs(("unique", "x"), ("dup", "y"), ("other", "z"), ("dup", "y"))
    findings = duplicate_questions(data, FIELDS)
    assert {f.sample_index for f in findings} == {1, 3}
    assert all(f.metadata["duplicate_indices"] == [1, 3] for f in findings)


def test_sample_id_from_field():
    fields = FieldMap(question="q", answer="a", id="id")
    data = [
        {"q": "same", "a": "yes", "id": "id-0"},
        {"q": "same", "a": "yes", "id": "id-1"},
    ]
    findings = duplicate_questions(data, fields)
    assert {f.sample_id for f in findings} == {"id-0", "id-1"}
