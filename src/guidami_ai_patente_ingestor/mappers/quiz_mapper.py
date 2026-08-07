import logging

from domain.entities.quiz import QuizImageEntity, QuizQuestionEntity
from guidami_ai_patente_ingestor.models.quiz import (
    CleanedQuizModel,
    EmbeddedQuizModel,
    EnrichedQuizModel,
    ParsedQuizItemModel,
    ParsedQuizModel,
)

logger = logging.getLogger(__name__)


class QuizMapper:
    """Backbone of the 1:1 transformations in the quiz bank pipeline.

    All methods are static and pure: each maps a model to the next one in
    the chain (`from_X_to_Y`). Dedup does not live here (it's not a 1:1
    mapping, but a collection-level operation): it lives in
    `DeduplicateQuizItemsService` (shared by preparation and indexing, chained to
    this mapper in the `flatten_quiz` and `map_to_embedded` steps of
    `quiz_flows.py`). The parsed→cleaned unnest+map (preparation) is instead
    expressed as `FlatMap(QuizMapper.from_parsed_to_cleaned_all)`.
    """

    @staticmethod
    def from_enriched_to_embedded(item: EnrichedQuizModel) -> EmbeddedQuizModel:
        """Maps an enriched question (flat) to `EmbeddedQuizModel`.

        Args:
            item: The enriched question to map (flat, self-contained model).

        Returns:
            `EmbeddedQuizModel` ready for embedding computation.
        """
        base = EmbeddedQuizModel(
            number=item.number,
            question_id=item.question_id,
            topic=item.topic,
            text=item.text.strip(),
            correct_answer=item.correct_answer,
            image_filename=item.image,
            image_description=item.image_description,
        )
        return base.model_copy(update={"quiz_metadata": item.quiz_metadata})

    @staticmethod
    def from_embedded_to_quiz_question(model: EmbeddedQuizModel) -> QuizQuestionEntity:
        """Maps an `EmbeddedQuizModel` to the `QuizQuestionEntity` entity.

        Discards `image_description` (not persisted). Spreads `quiz_metadata`
        onto the flat retrieval columns, including `vector_search_queries`
        (now persisted). If `quiz_metadata` is `None`, the four flat fields
        are `None`.

        Args:
            model: Embedded model with embedding already computed.

        Returns:
            `QuizQuestionEntity` entity ready for the store.
        """
        metadata = model.quiz_metadata
        if metadata is None:
            core_concepts = None
            exact_keywords = None
            rule_explanation = None
            vector_search_queries = None
        else:
            core_concepts = metadata.core_concepts
            exact_keywords = metadata.exact_keywords
            rule_explanation = metadata.rule_explanation
            vector_search_queries = metadata.vector_search_queries

        return QuizQuestionEntity(
            number=model.number,
            question_id=model.question_id,
            topic=model.topic,
            text=model.text,
            correct_answer=model.correct_answer,
            image_filename=model.image_filename,
            core_concepts=core_concepts,
            exact_keywords=exact_keywords,
            rule_explanation=rule_explanation,
            vector_search_queries=vector_search_queries,
        )

    @staticmethod
    def from_embedded_to_quiz_images(item: EmbeddedQuizModel) -> list[QuizImageEntity]:
        """Maps an embedded question's image to a `QuizImageEntity`, if it has one.

        Args:
            item: Embedded question, possibly carrying image_filename/image_description.

        Returns:
            `[QuizImageEntity]` when `image_filename` is set, `[]` otherwise — meant for
            `FlatMap`, so several questions sharing one image each safely upsert the same
            row (PD-8).
        """
        if item.image_filename is None:
            return []
        return [QuizImageEntity(filename=item.image_filename, description=item.image_description)]

    @staticmethod
    def from_cleaned_to_enriched(item: CleanedQuizModel) -> EnrichedQuizModel:
        """Maps a cleaned sub-question to `EnrichedQuizModel` (base-map, flat→flat).

        Args:
            item: The cleaned sub-question (flat, self-contained) to map.

        Returns:
            `EnrichedQuizModel` with `image_description=None` (to be populated by the enrichers).
        """
        return EnrichedQuizModel(
            question_id=item.question_id,
            topic=item.topic,
            number=item.number,
            text=item.text,
            correct_answer=item.correct_answer,
            image=item.image,
            image_description=None,
            quiz_metadata=None,
        )

    @staticmethod
    def from_parsed_to_cleaned(
        item: ParsedQuizItemModel, parent: ParsedQuizModel
    ) -> CleanedQuizModel:
        """Maps a parsed sub-question to `CleanedQuizModel` (denormalizes question_id/topic).

        Args:
            item: The sub-question to map.
            parent: The parent question providing `question_id` and `topic`.

        Returns:
            `CleanedQuizModel` (flat, self-contained) ready for upstream dedup,
            called for each sub-question by `from_parsed_to_cleaned_all`.
        """
        return CleanedQuizModel(
            question_id=parent.question_id,
            topic=parent.topic,
            number=item.number,
            text=item.text.strip(),
            correct_answer=item.correct_answer,
            image=item.image,
        )

    @staticmethod
    def from_parsed_to_cleaned_all(parent: ParsedQuizModel) -> list[CleanedQuizModel]:
        """Flattens a parsed (nested) question into its cleaned (flat) sub-questions.

        Maps each sub-question in `parent.sub_questions` by delegating to
        `from_parsed_to_cleaned`, preserving order. Does not deduplicate:
        deduplication is a separate transform (`DeduplicateQuizItemsService`),
        chained after `FlatMap(from_parsed_to_cleaned_all)` in
        `build_quiz_cleaning_flow`.

        Args:
            parent: The parsed question with nested sub-questions.

        Returns:
            Flat list of `CleanedQuizModel`, one per sub-question, in the
            same order as `parent.sub_questions`.
        """
        return [QuizMapper.from_parsed_to_cleaned(sub, parent) for sub in parent.sub_questions]
