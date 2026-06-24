import logging
from pathlib import PurePosixPath

from commons.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.models.quiz import (
    EmbeddableQuizModel,
    EnrichedQuizItemModel,
    EnrichedQuizModel,
)

logger = logging.getLogger(__name__)


class QuizMapper:
    """Backbone delle trasformazioni 1:1 della pipeline quiz bank.

    Tutti i metodi sono statici e puri: ciascuno mappa un modello nel
    successivo della catena (`from_X_to_Y`). Il flatten+dedup non è qui
    (non è un mapping 1:1, ma un'operazione su collezione): vive in
    `MapToEmbeddableStep`.
    """

    @staticmethod
    def from_enriched_quiz_item_to_embeddable(
        item: EnrichedQuizItemModel,
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
    def _image_filename(image: str | None) -> str | None:
        return PurePosixPath(image).name if image is not None else None
