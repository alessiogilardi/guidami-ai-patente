from collections import defaultdict
from collections.abc import Iterable

from commons.utils import deduplicate
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    QuizContextModel,
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel, ImageAnalysis


class RoadSignDescriberMapper:
    """Bidirectional translation between `EnrichedQuizModel` and the describer agent's DTOs.

    All methods are static and pure (no injected dependencies).
    """

    @staticmethod
    def from_enriched_quizzes_to_request(
        questions: list[EnrichedQuizModel],
    ) -> RoadSignDescriberRequest:
        """Builds a single request from every quiz that references the same image.

        Duplicate (topic, text) pairs are collapsed (first-seen order); a quiz text
        repeated verbatim under a different topic is also deduplicated (first-seen
        topic wins), so the prompt never lists the same question text twice.

        Args:
            questions: Quiz bank sub-questions that all reference the same image.

        Returns:
            `RoadSignDescriberRequest` with one context per distinct topic, each
            holding its distinct (and globally text-deduplicated) quiz texts.
        """
        unique = deduplicate(questions, key=lambda q: (q.topic, q.text))
        contexts = RoadSignDescriberMapper._from_enriched_quizzes_to_quiz_context(unique)

        return RoadSignDescriberRequest(contexts=contexts)

    @staticmethod
    def from_response_to_enriched_quiz(
        question: EnrichedQuizModel,
        response: RoadSignDescriberResponse,
    ) -> EnrichedQuizModel:
        """Applies the description produced by the agent to the enriched sub-question.

        Sets `image_description` (flat, downstream) and `image_analysis` (structured,
        debug-only, includes `visual_analysis`).

        Args:
            question: Original sub-question to apply the description to.
            response: Structured agent response with the sign's name and description.

        Returns:
            New `EnrichedQuizModel` with `image_description` and `image_analysis` populated.
        """
        description = f"{response.name}. {response.description}"
        analysis = ImageAnalysis(
            visual_analysis=response.visual_analysis,
            name=response.name,
            description=response.description,
        )
        return question.model_copy(
            update={"image_description": description, "image_analysis": analysis}
        )

    @staticmethod
    def _from_enriched_quizzes_to_quiz_context(
        questions: Iterable[EnrichedQuizModel],
    ) -> list[QuizContextModel]:
        contexts: defaultdict[str, list[str]] = defaultdict(list)
        seen_texts: set[str] = set()
        for quiz in questions:
            if quiz.text not in seen_texts:
                contexts[quiz.topic].append(quiz.text)
                seen_texts.add(quiz.text)

        return [QuizContextModel(topic=topic, texts=texts) for topic, texts in contexts.items()]
