import logging
from pathlib import Path

from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import RoadSignDescriberResponse
from guidami_ai_patente_ingestor.mappers.agents import RoadSignDescriberMapper
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel

logger = logging.getLogger(__name__)

_DedupeKey = tuple[str, str, str]  # (image, topic, text)


class ImageDescriptionEnricher(UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]]):
    """Arricchisce le sotto-domande con la descrizione del segnale stradale.

    La chiave di dedup è `(image, topic, text)`: stessa immagine in contesti diversi
    genera chiamate separate per descrizioni contestualizzate; duplicati esatti vengono
    collassati.
    """

    def __init__(self, road_sign_describer: RoadSignDescriberAgent, images_dir: Path) -> None:
        """Inietta l'agente di descrizione e la directory delle immagini.

        Args:
            road_sign_describer: Agente vision LLM che descrive un segnale.
            images_dir: Directory che contiene i file immagine del quiz bank.
        """
        self._road_sign_describer = road_sign_describer
        self._images_dir = images_dir

    def execute(self, request: list[EnrichedQuizModel]) -> list[EnrichedQuizModel]:
        """Valorizza `image_description` su ogni sotto-domanda con immagine.

        Args:
            request: Sotto-domande enriched (flat) da arricchire.

        Returns:
            Nuove `EnrichedQuizModel` con `image_description` valorizzato sulle
            sotto-domande la cui immagine è stata descritta con successo.
        """
        descriptions = self._describe_questions_with_images(request)
        return [
            RoadSignDescriberMapper.from_response_to_enriched_quiz(
                q, descriptions[(q.image, q.topic, q.text)]
            )
            if q.image and (q.image, q.topic, q.text) in descriptions
            else q
            for q in request
        ]

    def _describe_questions_with_images(
        self, questions: list[EnrichedQuizModel]
    ) -> dict[_DedupeKey, RoadSignDescriberResponse]:
        seen: set[_DedupeKey] = set()
        results: dict[_DedupeKey, RoadSignDescriberResponse] = {}
        for q in questions:
            if q.image is None:
                continue
            key: _DedupeKey = (q.image, q.topic, q.text)
            if key in seen:
                continue
            seen.add(key)
            path = self._images_dir / q.image
            if not path.exists():
                logger.warning("Image file not found, skipping description: %s", path)
                continue
            try:
                request = RoadSignDescriberMapper.from_enriched_quiz_to_request(q)
                results[key] = self._road_sign_describer.run_sync(request, images=(path,))
            except Exception:
                logger.warning("Failed to describe image, skipping: %s", path, exc_info=True)
        return results
