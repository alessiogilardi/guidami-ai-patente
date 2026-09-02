"""The writer's contract: grounded in the supplied commas, and nothing else (FR-10, AD-14)."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente.agents.explanation_writer.dto import (
    ExplanationWriterRequest,
    ExplanationWriterResponse,
)
from guidami_ai_patente.models import LabeledComma


def _comma(judge_rank: int, comma_number: str) -> LabeledComma:
    return LabeledComma(
        source="cds",
        article_number="157",
        article_title="Arresto, fermata e sosta dei veicoli",
        comma_number=comma_number,
        text="È vietata la sosta negli spazi riservati.",
        judge_rank=judge_rank,
    )


def _request(**overrides: object) -> ExplanationWriterRequest:
    fields: dict[str, object] = {
        "quiz_text": "Il segnale vieta la sosta?",
        "correct_answer": True,
        "commas": [_comma(1, "3"), _comma(2, "5")],
    }
    fields.update(overrides)
    return ExplanationWriterRequest(**fields)  # pyright: ignore[reportArgumentType]


def test_the_comma_block_numbers_from_one() -> None:
    """The ordinals the writer reports back index this block, so it starts at 1."""
    block = _request().commas_block

    assert block.startswith("1. [cds art. 157 c. 3 — Arresto, fermata e sosta dei veicoli]")
    assert "\n2. [cds art. 157 c. 5 —" in block


def test_the_block_is_ordered_as_supplied() -> None:
    """FR-5 hands them over ordered by judge_rank; the writer must see that order."""
    block = _request(commas=[_comma(1, "9"), _comma(2, "1")]).commas_block

    assert block.index("c. 9") < block.index("c. 1")


def test_no_comma_is_refused() -> None:
    """FR-7: the writer is never invoked without supporting commas."""
    with pytest.raises(ValidationError):
        _request(commas=[])


def test_the_answers_render_as_italian_literals() -> None:
    request = _request(correct_answer=False, submitted_answer=True)

    assert (request.correct_answer_it, request.submitted_answer_it) == ("Falso", "Vero")


def test_an_omitted_submitted_answer_renders_as_not_communicated() -> None:
    """FR-11: without `submitted` the writer must produce a neutral explanation."""
    assert _request().submitted_answer_it == "Non comunicata"


def test_a_missing_image_renders_as_the_italian_fallback() -> None:
    assert _request().image_description_it == "Nessuna immagine allegata a questa domanda."


def test_an_empty_explanation_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExplanationWriterResponse(explanation="", cited_comma_numbers=[1])


def test_citing_nothing_is_rejected() -> None:
    """AD-14: an explanation that cites no comma is ungrounded by construction."""
    with pytest.raises(ValidationError):
        ExplanationWriterResponse(explanation="Perché la norma lo vieta.", cited_comma_numbers=[])


def test_a_repeated_ordinal_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExplanationWriterResponse(
            explanation="Perché la norma lo vieta.", cited_comma_numbers=[1, 1]
        )
