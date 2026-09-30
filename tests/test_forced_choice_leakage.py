from inspect_dataset._types import FieldMap
from inspect_dataset.scanners.forced_choice_leakage import forced_choice_leakage

FIELDS = FieldMap(question="q", answer="a")


def rec(question: str, answer: str) -> list[dict]:
    return [{"q": question, "a": answer}]


def test_no_or_no_finding():
    assert forced_choice_leakage(rec("is this an mri?", "yes"), FIELDS) == []


def test_or_answer_matches_flagged():
    findings = forced_choice_leakage(rec("is this an mri or a ct scan?", "mri"), FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "forced_choice_leakage"
    assert f.severity == "medium"
    assert f.category == "leakage"


def test_or_answer_not_in_options_no_finding():
    # "or" present but answer is unrelated
    assert forced_choice_leakage(rec("is this big or small?", "yes"), FIELDS) == []


def test_left_option_matched():
    findings = forced_choice_leakage(rec("is the lesion on the left or right?", "left"), FIELDS)
    assert len(findings) == 1


def test_right_option_matched():
    findings = forced_choice_leakage(rec("is the lesion on the left or right?", "right"), FIELDS)
    assert len(findings) == 1


def test_case_insensitive_match():
    findings = forced_choice_leakage(
        rec("is this supratentorial or infratentorial?", "Supratentorial"), FIELDS
    )
    assert len(findings) == 1


def test_article_stripped_from_options():
    # "an mri" → "mri" after stripping article
    findings = forced_choice_leakage(rec("is this an mri or a ct scan?", "ct scan"), FIELDS)
    assert len(findings) == 1


def test_multiple_records_only_matching_flagged():
    records = [
        {"q": "is this an mri or ct?", "a": "mri"},  # flagged
        {"q": "what is the diagnosis?", "a": "cancer"},  # not flagged
        {"q": "is this normal or abnormal?", "a": "yes"},  # not flagged (answer not an option)
    ]
    findings = forced_choice_leakage(records, FIELDS)
    assert len(findings) == 1
    assert findings[0].sample_index == 0


def test_metadata_contains_options():
    findings = forced_choice_leakage(rec("is this an mri or a ct scan?", "mri"), FIELDS)
    assert "options" in findings[0].metadata
    assert len(findings[0].metadata["options"]) >= 2


def test_empty_answer_skipped():
    prompt = '"Which is your preferred political party: Democrats or Republicans?"'
    assert forced_choice_leakage(rec(prompt, ""), FIELDS) == []
    assert forced_choice_leakage(rec(prompt, "  "), FIELDS) == []


def test_single_letter_answer_does_not_match_word_ending():
    assert forced_choice_leakage(rec("Is the cell prokaryotic or eukaryotic?", "C"), FIELDS) == []
    assert forced_choice_leakage(rec("Was the soldier wounded or killed?", "D"), FIELDS) == []


def test_mid_word_suffix_not_matched():
    assert (
        forced_choice_leakage(rec("Is this hypertension or hypotension?", "tension"), FIELDS) == []
    )
    assert (
        forced_choice_leakage(rec("is x-ring chain or o-ring chain better?", "ring chain"), FIELDS)
        == []
    )


def test_answer_with_article_and_punctuation_matches():
    assert len(forced_choice_leakage(rec("is this a ct or an mri?", "an MRI."), FIELDS)) == 1


BOOLQ_PROMPT = (
    "Given a passage, answer the subsequent question with either Yes or No. "
    "Include nothing else in your response.\n\n"
    "Passage: It has higher performance (in terms of durability, lifetime, and power loss) "
    "than non-O-ring chain as it has less friction than O-ring chain which also increases "
    "reliability. It can last twice as long as the O-ring chain.\n\n"
    "Question: is x-ring chain better than o-ring chain"
)

DROP_PASSAGE = (
    "Passage: In the city, the age distribution of the population shows 21.8% under the "
    "age of 18, 13.1% from 18 to 24, 31.7% from 25 to 44, 20.1% from 45 to 64, and 13.2% "
    "who were 65 years of age or older. The median age was 34 years. For every 100 females, "
    "there were 87.1 males.\n"
)


def test_instruction_or_not_treated_as_options():
    assert forced_choice_leakage(rec(BOOLQ_PROMPT, "Yes"), FIELDS) == []
    assert forced_choice_leakage(rec(BOOLQ_PROMPT, "No"), FIELDS) == []


def test_passage_or_not_treated_as_options():
    prompt = DROP_PASSAGE + "Question: Which age group had the fourth most people?\nAnswer:"
    assert forced_choice_leakage(rec(prompt, "65 years of age"), FIELDS) == []


def test_question_sentence_after_passage_still_flagged():
    prompt = (
        DROP_PASSAGE
        + "Question: Which age group is larger: under the age of 18 or 18 to 24?\nAnswer:"
    )
    findings = forced_choice_leakage(rec(prompt, "under the age of 18"), FIELDS)
    assert len(findings) == 1


def test_comparison_question_with_names_flagged():
    prompt = (
        "Passage: ...\n"
        "Question: Which player scored more field goals, Joe Nedney or Olindo Mare?\n"
        "Answer:"
    )
    assert len(forced_choice_leakage(rec(prompt, "Joe Nedney"), FIELDS)) == 1
    assert len(forced_choice_leakage(rec(prompt, "Olindo Mare"), FIELDS)) == 1


def test_only_last_question_counts():
    # Few-shot exemplars before the real question do not offer its options.
    prompt = "Q: Is the sky blue or green?\nA: blue\n\nQ: What colour is grass?"
    assert forced_choice_leakage(rec(prompt, "blue"), FIELDS) == []


def test_or_outside_question_sentence_ignored():
    prompt = "Hold the brush with your left or right hand. Which hand do most painters use?"
    assert forced_choice_leakage(rec(prompt, "right"), FIELDS) == []


def test_head_noun_of_option_matches():
    q = (
        "When rock formations are found on top of a fault, "
        "they must be older or younger than the fault?"
    )
    assert len(forced_choice_leakage(rec(q, "younger than the fault"), FIELDS)) == 1
    assert (
        len(
            forced_choice_leakage(
                rec(
                    "Which is older the British Empire or the Ethiopian Empire?", "Ethiopian Empire"
                ),
                FIELDS,
            )
        )
        == 1
    )


def test_answer_elsewhere_in_question_sentence_not_matched():
    # "heart" is in the question but is not next to "or".
    assert forced_choice_leakage(rec("is the heart size smaller or larger?", "heart"), FIELDS) == []


def test_no_question_mark_no_finding():
    # BBH boolean expressions use "or" as an operator, not to offer options.
    assert forced_choice_leakage(rec("not ( True ) or ( False ) is", "True"), FIELDS) == []


def test_metadata_reports_question_sentence():
    prompt = (
        DROP_PASSAGE
        + "Question: Which age group is larger: under the age of 18 or 18 to 24?\nAnswer:"
    )
    f = forced_choice_leakage(rec(prompt, "under the age of 18"), FIELDS)[0]
    assert f.metadata["question"] == prompt
    assert (
        f.metadata["question_sentence"]
        == "Question: Which age group is larger: under the age of 18 or 18 to 24?"
    )
    assert "Passage" not in f.explanation


def test_comma_before_or_flagged():
    q = "Question: Which happened first, the Diet of Worms, or the Protestation at Speyer?"
    assert len(forced_choice_leakage(rec(q, "Diet of Worms"), FIELDS)) == 1
    assert len(forced_choice_leakage(rec(q, "Protestation at Speyer"), FIELDS)) == 1


def test_list_of_options_flagged():
    q = "Question: Which was not grown there, rubber cultivation, cattle, or coffee?"
    assert len(forced_choice_leakage(rec(q, "cattle"), FIELDS)) == 1
    assert len(forced_choice_leakage(rec(q, "rubber cultivation"), FIELDS)) == 1


def test_initial_does_not_end_the_sentence():
    q = "Question: Who was elected, Leandro N. Alem or Hipólito Yrigoyen?"
    assert len(forced_choice_leakage(rec(q, "Leandro N. Alem"), FIELDS)) == 1
