"""Tests for QuestionExplainerRequest/Response DTOs (FR-2, FR-6)."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente.agents.question_explainer.dto import (
    QuestionExplainerRequest,
    QuestionExplainerResponse,
)
from guidami_ai_patente.models import GlossaryCandidate


def _candidate(id_: int, term: str) -> GlossaryCandidate:
    return GlossaryCandidate(
        id=id_,
        source="cds",
        article_number="3",
        comma_number="1",
        term=term,
        definition=f"Definizione di {term}.",
        term_ru="x",
    )


def test_question_explainer_request_has_no_answer_field() -> None:
    """AD-4: structurally answer-blind — no field could ever carry the answer."""
    fields = QuestionExplainerRequest.model_fields.keys()
    assert not {"correct_answer", "rule_explanation", "core_concepts", "topic"} & set(fields)


def test_candidates_block_renders_one_line_per_candidate_starting_at_one() -> None:
    request = QuestionExplainerRequest(
        text="La carreggiata è larga?",
        image_description=None,
        candidates=[_candidate(1, "carreggiata"), _candidate(2, "banchina")],
    )
    assert "1. [carreggiata]" in request.candidates_block
    assert "2. [banchina]" in request.candidates_block


def test_question_explainer_response_rejects_repeated_ordinal() -> None:
    with pytest.raises(ValidationError):
        QuestionExplainerResponse(explanation="Testo.", cited_term_numbers=[1, 1])


def test_question_explainer_response_allows_empty_citations() -> None:
    """Unlike the legal stage, a question may need no official term at all (FR-6)."""
    response = QuestionExplainerResponse(explanation="Testo semplice, nessun termine tecnico.")
    assert response.cited_term_numbers == []
