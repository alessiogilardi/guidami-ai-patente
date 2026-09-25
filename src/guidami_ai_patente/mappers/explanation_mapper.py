"""Maps the explanation outcome onto the wire contract."""

from guidami_ai_patente.api.schemas.quiz_explanation import (
    CitationResponse,
    CitedGlossaryTermResponse,
    ProvenanceResponse,
    QuizExplanationResponse,
)
from guidami_ai_patente.models import CurrentLabeling, Explanation, LabeledComma


class ExplanationMapper:
    """Turns an `Explanation` into the response the client receives.

    Two renamings and nothing else: `judge_rank` becomes `rank`, and `result` becomes
    `status`. `CurrentLabeling` is projected down to the three provenance fields FR-5
    names — its `id` and `rationale` are internal (the latter is passed through
    separately, as `judge_rationale`, precisely so it is an explicit choice rather than
    a leak). Static, like every mapper in this repo.
    """

    @staticmethod
    def from_explanation_to_response(explanation: Explanation) -> QuizExplanationResponse:
        """Builds the wire response for either outcome."""
        return QuizExplanationResponse(
            status=explanation.result,
            explanation=explanation.explanation,
            citations=[
                ExplanationMapper._from_comma_to_citation(comma) for comma in explanation.citations
            ],
            provenance=(
                None
                if explanation.provenance is None
                else ExplanationMapper._from_labeling_to_provenance(explanation.provenance)
            ),
            reason=explanation.reason,
            judge_rationale=explanation.judge_rationale,
            term_explanation=explanation.term_explanation,
            translation_hints=[
                CitedGlossaryTermResponse(
                    term=hint.term,
                    definition=hint.definition,
                    term_ru=hint.term_ru,
                    origin=hint.origin,
                )
                for hint in explanation.translation_hints
            ],
        )

    @staticmethod
    def _from_comma_to_citation(comma: LabeledComma) -> CitationResponse:
        """Renames `judge_rank` to the client-facing `rank`."""
        return CitationResponse(
            source=comma.source,
            article_number=comma.article_number,
            article_title=comma.article_title,
            comma_number=comma.comma_number,
            text=comma.text,
            rank=comma.judge_rank,
        )

    @staticmethod
    def _from_labeling_to_provenance(labeling: CurrentLabeling) -> ProvenanceResponse:
        """Projects the labeling down to the three fields FR-5 names."""
        return ProvenanceResponse(
            origin=labeling.origin,
            human_validated=labeling.human_validated,
            judge_model=labeling.judge_model,
        )
