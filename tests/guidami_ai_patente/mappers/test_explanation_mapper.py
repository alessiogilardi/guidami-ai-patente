"""The domain outcome, on the wire (FR-5, FR-7)."""

from guidami_ai_patente.enums import ExplanationResult, InsufficientKnowledgeReason
from guidami_ai_patente.mappers import ExplanationMapper
from guidami_ai_patente.models import CurrentLabeling, Explanation, LabeledComma


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
