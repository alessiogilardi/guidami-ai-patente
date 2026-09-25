"""The domain outcome, on the wire (FR-5, FR-7)."""

from guidami_ai_patente.api.schemas.quiz_explanation import CitedGlossaryTermResponse
from guidami_ai_patente.enums import (
    ExplanationResult,
    GlossaryTermOrigin,
    InsufficientKnowledgeReason,
)
from guidami_ai_patente.mappers import ExplanationMapper
from guidami_ai_patente.models import CitedGlossaryTerm, CurrentLabeling, Explanation, LabeledComma


def _comma(judge_rank: int) -> LabeledComma:
    return LabeledComma(
        source="cds",
        article_number="157",
        article_title="Sosta",
        comma_number="3",
        text="Testo.",
        judge_rank=judge_rank,
    )


def _labeling() -> CurrentLabeling:
    return CurrentLabeling(
        id=7,
        rationale="motivazione",
        has_supporting_commas=True,
        origin="live",
        judge_model="openrouter/google/gemini-2.5-flash-lite",
        human_validated=False,
    )


def test_an_explained_result_carries_its_citations_and_provenance() -> None:
    response = ExplanationMapper.from_explanation_to_response(
        Explanation(
            result=ExplanationResult.EXPLAINED,
            explanation="La sosta è vietata.",
            citations=(_comma(1), _comma(2)),
            provenance=_labeling(),
        )
    )

    assert response.status is ExplanationResult.EXPLAINED
    assert [citation.rank for citation in response.citations] == [1, 2]
    assert response.provenance is not None
    assert response.provenance.judge_model == "openrouter/google/gemini-2.5-flash-lite"
    assert response.reason is None


def test_the_citation_exposes_rank_not_judge_rank() -> None:
    """FR-5 names the field `rank`: the client has no notion of a judge."""
    response = ExplanationMapper.from_explanation_to_response(
        Explanation(
            result=ExplanationResult.EXPLAINED,
            explanation="La sosta è vietata.",
            citations=(_comma(1),),
            provenance=_labeling(),
        )
    )

    dumped = response.citations[0].model_dump()

    assert "rank" in dumped
    assert "judge_rank" not in dumped


def test_a_refusal_carries_the_reason_and_no_prose() -> None:
    response = ExplanationMapper.from_explanation_to_response(
        Explanation(
            result=ExplanationResult.INSUFFICIENT_KNOWLEDGE,
            reason=InsufficientKnowledgeReason.NOT_INDEXED,
        )
    )

    assert response.status is ExplanationResult.INSUFFICIENT_KNOWLEDGE
    assert (response.explanation, response.citations, response.provenance) == (None, [], None)
    assert response.reason is InsufficientKnowledgeReason.NOT_INDEXED


def test_term_explanation_and_hints_are_mapped_through() -> None:
    response = ExplanationMapper.from_explanation_to_response(
        Explanation(
            result=ExplanationResult.EXPLAINED,
            explanation="La sosta è vietata.",
            citations=(_comma(1),),
            provenance=_labeling(),
            term_explanation="La domanda chiede...",
            translation_hints=(
                CitedGlossaryTerm(
                    term="x",
                    definition="y",
                    term_ru="z",
                    origin=GlossaryTermOrigin.VERBATIM_CORPUS,
                ),
            ),
        )
    )

    assert response.term_explanation == "La domanda chiede..."
    assert response.translation_hints == [
        CitedGlossaryTermResponse(
            term="x", definition="y", term_ru="z", origin=GlossaryTermOrigin.VERBATIM_CORPUS
        )
    ]


def test_the_hints_origin_is_mapped_through() -> None:
    """FR-8: an agent-generated hint's origin must survive onto the wire response."""
    response = ExplanationMapper.from_explanation_to_response(
        Explanation(
            result=ExplanationResult.EXPLAINED,
            explanation="La sosta è vietata.",
            citations=(_comma(1),),
            provenance=_labeling(),
            translation_hints=(
                CitedGlossaryTerm(
                    term="revoca",
                    definition="...",
                    term_ru=None,
                    origin=GlossaryTermOrigin.AGENT_GENERATED,
                ),
            ),
        )
    )

    assert response.translation_hints[0].origin is GlossaryTermOrigin.AGENT_GENERATED


def test_a_refusal_still_carries_term_explanation_and_hints() -> None:
    """AD-1: independent of `result` — the coherent-shape validator (Task 7) allows this."""
    response = ExplanationMapper.from_explanation_to_response(
        Explanation(
            result=ExplanationResult.INSUFFICIENT_KNOWLEDGE,
            reason=InsufficientKnowledgeReason.NOT_INDEXED,
            term_explanation="La domanda chiede...",
            translation_hints=(
                CitedGlossaryTerm(
                    term="x",
                    definition="y",
                    term_ru="z",
                    origin=GlossaryTermOrigin.VERBATIM_CORPUS,
                ),
            ),
        )
    )

    assert response.status is ExplanationResult.INSUFFICIENT_KNOWLEDGE
    assert response.term_explanation == "La domanda chiede..."
