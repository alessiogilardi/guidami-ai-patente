import logging
from pathlib import PurePosixPath

from commons.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.models.quiz import (
    CleanedQuizModel,
    EmbeddableQuizModel,
    EnrichedQuizModel,
    ParsedQuizItemModel,
    ParsedQuizModel,
)

logger = logging.getLogger(__name__)


class QuizMapper:
    """Backbone delle trasformazioni 1:1 della pipeline quiz bank.

    Tutti i metodi sono statici e puri: ciascuno mappa un modello nel
    successivo della catena (`from_X_to_Y`). Il flatten+dedup non è qui
    (non è un mapping 1:1, ma un'operazione su collezione): vive in
    `FlattenQuizStep` (preparation, parsed→cleaned) e in `MapToEmbeddableStep`
    (indexing, enriched→embeddable).
    """

    @staticmethod
    def from_enriched_quiz_item_to_embeddable(
        item: EnrichedQuizModel,
        parent: EnrichedQuizModel,
    ) -> EmbeddableQuizModel:
        """Mappa una sotto-domanda enriched in `EmbeddableQuizModel`.

        Args:
            item: La sotto-domanda da mappare.
            parent: La domanda madre che fornisce `question_id` e `topic`.

        Returns:
            `EmbeddableQuizModel` pronto per il calcolo dell'embedding.
        """
        return EmbeddableQuizModel(
            number=item.number,
            question_id=parent.question_id,
            topic=parent.topic,
            text=item.text.strip(),
            correct_answer=item.correct_answer,
            image_filename=QuizMapper._image_filename(item.image),
            image_description=item.image_description,
        )

    @staticmethod
    def from_embeddable_to_quiz_question(model: EmbeddableQuizModel) -> QuizQuestion:
        """Mappa un `EmbeddableQuizModel` nell'entità `QuizQuestion`.

        Scarta `image_description` (non persistita), mantiene `embedding`.

        Args:
            model: Modello embeddable con embedding già calcolato.

        Returns:
            Entità `QuizQuestion` pronta per lo store.
        """
        return QuizQuestion(
            number=model.number,
            question_id=model.question_id,
            topic=model.topic,
            text=model.text,
            correct_answer=model.correct_answer,
            image_filename=model.image_filename,
            embedding=model.embedding,
        )

    @staticmethod
    def from_cleaned_to_enriched(item: CleanedQuizModel) -> EnrichedQuizModel:
        """Mappa una sotto-domanda cleaned in `EnrichedQuizModel` (base-map, flat→flat).

        Args:
            item: La sotto-domanda cleaned (flat, auto-contenuta) da mappare.

        Returns:
            `EnrichedQuizModel` con `image_description=None` (da popolare dagli enricher).
        """
        return EnrichedQuizModel(
            question_id=item.question_id,
            topic=item.topic,
            number=item.number,
            text=item.text,
            correct_answer=item.correct_answer,
            image=item.image,
            image_description=None,
        )

    @staticmethod
    def from_parsed_to_cleaned(
        item: ParsedQuizItemModel, parent: ParsedQuizModel
    ) -> CleanedQuizModel:
        """Mappa una sotto-domanda parsed in `CleanedQuizModel` (denormalizza question_id/topic).

        Args:
            item: La sotto-domanda da mappare.
            parent: La domanda madre che fornisce `question_id` e `topic`.

        Returns:
            `CleanedQuizModel` (flat, auto-contenuto) pronto per il dedup a monte
            (`FlattenQuizStep`).
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
    def _image_filename(image: str | None) -> str | None:
        return PurePosixPath(image).name if image is not None else None
