from __future__ import annotations

from novaxis_core.intake import out_of_area, prompt_block, status
from novaxis_core.packspec import IntakeQuestion

Q = [
    IntakeQuestion(key="name", ask="Name?"),
    IntakeQuestion(key="problem_type", ask="Which?", type="choice", choices=["leak", "service"]),
    IntakeQuestion(key="symptom", ask="What?", skip_if={"problem_type": "service"}),
    IntakeQuestion(key="age", ask="Age?", required=False),
    IntakeQuestion(key="postcode", ask="Postcode?", type="postcode"),
    IntakeQuestion(key="phone", ask="Phone?", type="phone"),
]


def test_asks_in_order_and_skips_optional() -> None:
    st = status(Q, {})
    assert not st.complete and st.next_question is not None and st.next_question.key == "name"
    st = status(Q, {"name": "Al", "problem_type": "leak"})
    assert st.next_question.key == "symptom"  # type: ignore[union-attr]
    st = status(Q, {"name": "Al", "problem_type": "leak", "symptom": "drip"})
    assert st.next_question.key == "postcode", "age is optional"  # type: ignore[union-attr]


def test_skip_logic() -> None:
    st = status(Q, {"name": "Al", "problem_type": "service"})
    assert st.next_question.key == "postcode"  # type: ignore[union-attr]


def test_invalid_answers_are_asked_again() -> None:
    st = status(Q, {"name": "Al", "problem_type": "nonsense"})
    assert st.next_question.key == "problem_type" and "problem_type" in st.invalid  # type: ignore[union-attr]
    st = status(
        Q, {"name": "Al", "problem_type": "leak", "symptom": "x", "postcode": "not a postcode"}
    )
    assert st.next_question.key == "postcode"  # type: ignore[union-attr]
    st = status(
        Q,
        {
            "name": "Al",
            "problem_type": "leak",
            "symptom": "x",
            "postcode": "SW1A 1AA",
            "phone": "call me",
        },
    )
    assert st.next_question.key == "phone"  # type: ignore[union-attr]


def test_complete_and_us_zip_and_uk_postcode() -> None:
    st = status(
        Q,
        {
            "name": "Al",
            "problem_type": "leak",
            "symptom": "x",
            "postcode": "90210",
            "phone": "+1 555 010 0000",
        },
    )
    assert st.complete and st.next_question is None
    assert status(
        Q,
        {
            "name": "Al",
            "problem_type": "leak",
            "symptom": "x",
            "postcode": "sw1a1aa",
            "phone": "07700900123",
        },
    ).complete


def test_prompt_block_names_next_question_and_key() -> None:
    block = prompt_block(Q, {"name": "Al"})
    assert (
        "- name: answered" in block and "- problem_type (one of: leak, service): missing" in block
    )
    assert (
        "Ask next, in your own words: Which?" in block and "under the key 'problem_type'" in block
    )
    done = prompt_block(
        Q, {"name": "Al", "problem_type": "service", "postcode": "SW1A 1AA", "phone": "07700900123"}
    )
    assert "Intake is complete." in done and "Do not ask the customer any" in done
    assert "Ask next" not in done


def test_out_of_area() -> None:
    assert out_of_area("M1 1AE", ["SW1", "SE1"])
    assert not out_of_area("sw1a 1aa", ["SW1", "SE1"])
    assert not out_of_area("M1 1AE", [])
    assert not out_of_area(None, ["SW1"])
