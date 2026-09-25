"""Tests for GlossaryEnricherRequest/Response DTOs (FR-2, FR-3, AD-3)."""

import pytest
from pydantic import ValidationError

from domain.models.retrieval import RetrievedComma
from guidami_ai_patente.agents.glossary_enricher.dto import (
    GlossaryEnricherEntryDto,
    GlossaryEnricherRequest,
    GlossaryEnricherResponse,
)


def _comma(comma_number: str, text: str) -> RetrievedComma:
    return RetrievedComma(
        id=1,
        source="cds",
        article_number="157",
        article_title="Sosta",
        comma_number=comma_number,
        text=text,
        distance=0.1,
    )


def test_glossary_enricher_request_has_no_answer_field() -> None:
    """FR-2: structurally answer-blind, mirroring QuestionExplainerRequest (AD-2 note)."""
    fields = GlossaryEnricherRequest.model_fields.keys()
    assert not {"correct_answer", "rule_explanation", "core_concepts", "topic"} & set(fields)


def test_commas_block_renders_one_line_per_comma_starting_at_one() -> None:
    request = GlossaryEnricherRequest(
        text="Cos'è la sosta?",
        image_description=None,
        commas=[_comma("1", "È vietata la sosta."), _comma("2", "Salvo diversa segnalazione.")],
    )
    assert "1. [cds art. 157 comma 1]" in request.commas_block
    assert "2. [cds art. 157 comma 2]" in request.commas_block


def test_an_empty_comma_list_is_accepted() -> None:
    """FR-2: find_with_vector returning None still lets the agent run."""
    request = GlossaryEnricherRequest(text="Cos'è la sosta?")
    assert request.commas == []
    assert request.commas_block == ""


def test_glossary_enricher_response_allows_empty_entries() -> None:
    """FR-1: a genuinely term-free question yields an empty list, not an error."""
    response = GlossaryEnricherResponse()
    assert response.entries == []


def test_glossary_enricher_response_rejects_a_case_variant_duplicate() -> None:
    with pytest.raises(ValidationError):
        GlossaryEnricherResponse(
            entries=[
                GlossaryEnricherEntryDto(term="Revoca", definition="a"),
                GlossaryEnricherEntryDto(term="revoca", definition="b"),
            ]
        )


def test_glossary_enricher_response_rejects_a_whitespace_variant_duplicate() -> None:
    """AD-6/AD-3: the dedup key is term.strip().casefold(), not bare casefold()."""
    with pytest.raises(ValidationError):
        GlossaryEnricherResponse(
            entries=[
                GlossaryEnricherEntryDto(term=" revoca", definition="a"),
                GlossaryEnricherEntryDto(term="revoca ", definition="b"),
            ]
        )


def test_glossary_enricher_response_allows_distinct_terms() -> None:
    response = GlossaryEnricherResponse(
        entries=[
            GlossaryEnricherEntryDto(term="revoca", definition="a"),
            GlossaryEnricherEntryDto(term="sospensione", definition="b"),
        ]
    )
    assert len(response.entries) == 2
