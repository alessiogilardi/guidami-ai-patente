from guidami_ai_patente_ingestor.agents.dto.norm_reference_describer import (
    NormReferenceDescriberRequest,
    NormReferenceDescriberResponse,
)
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel, QuizMetadata


class NormReferenceDescriberMapper:
    """Bidirectional translation between `EnrichedQuizModel` and the NormReferenceDescriber DTOs.

    All methods are static and pure (no injected dependencies).
    """

    @staticmethod
    def from_enriched_quiz_to_request(
        question: EnrichedQuizModel,
    ) -> NormReferenceDescriberRequest:
        """Builds the agent request from an enriched sub-question.

        Args:
            question: Quiz bank sub-question with topic, text, and correct answer.

        Returns:
            `NormReferenceDescriberRequest` with the prompt-relevant fields.
        """
        return NormReferenceDescriberRequest(
            topic=question.topic,
            text=question.text,
            correct_answer=question.correct_answer,
            image_description=(
                question.image_description or "Nessuna immagine allegata a questa domanda."
            ),
        )

    @staticmethod
    def from_response_to_enriched_quiz(
        question: EnrichedQuizModel,
        response: NormReferenceDescriberResponse,
    ) -> EnrichedQuizModel:
        """Applies the norm metadata produced by the agent to the enriched sub-question.

        Args:
            question: Original sub-question to apply the metadata to.
            response: Structured agent response with the norm metadata.

        Returns:
            New `EnrichedQuizModel` with `quiz_metadata` populated.
        """
        return question.model_copy(
            update={
                "quiz_metadata": QuizMetadata(
                    core_concepts=response.core_concepts,
                    exact_keywords=response.exact_keywords,
                    vector_search_queries=response.vector_search_queries,
                    rule_explanation=response.rule_explanation,
                )
            }
        )
