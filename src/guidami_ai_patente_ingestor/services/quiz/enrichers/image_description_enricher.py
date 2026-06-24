import logging
from pathlib import Path

from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel

from .quiz_enricher import QuizEnricher

logger = logging.getLogger(__name__)


class ImageDescriptionEnricher(QuizEnricher):
    """Arricchisce le sotto-domande con la descrizione del segnale stradale.

    Una sola chiamata vision per immagine unica (dedup), non per occorrenza:
    più sotto-domande possono condividere la stessa immagine.
    """

    def __init__(self, road_sign_describer: RoadSignDescriberAgent, images_dir: Path) -> None:
        """Inietta l'agente di descrizione e la directory delle immagini.

        Args:
            road_sign_describer: Agente vision LLM che descrive un segnale.
            images_dir: Directory che contiene i file immagine del quiz bank.
        """
        self._road_sign_describer = road_sign_describer
        self._images_dir = images_dir

    def enrich(self, questions: list[EnrichedQuizModel]) -> list[EnrichedQuizModel]:
        """Valorizza `image_description` su ogni sotto-domanda con immagine.

        Args:
            questions: Sotto-domande enriched (flat) da arricchire.

        Returns:
            Nuove `EnrichedQuizModel` con `image_description` valorizzato sulle
            sotto-domande la cui immagine è stata descritta con successo.
        """
        unique_images = {q.image for q in questions if q.image is not None}
        descriptions = self._describe_images(unique_images)

        return [
            question.model_copy(
                update={
                    "image_description": (
                        descriptions.get(question.image) if question.image is not None else None
                    )
                }
            )
            for question in questions
        ]

    def _describe_images(self, images: set[str]) -> dict[str, str]:
        descriptions: dict[str, str] = {}
        for image in images:
            path = self._images_dir / image
            if not path.exists():
                logger.warning(f"Image file not found, skipping description: {path}")
                continue
            try:
                desc = self._road_sign_describer.describe(path)
            except Exception:
                logger.warning(f"Failed to describe image, skipping: {path}", exc_info=True)
                continue
            descriptions[image] = f"{desc.name}. {desc.description}"
        return descriptions
