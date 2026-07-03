import logging

from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.agents import NormReferenceDescriberAgent
from guidami_ai_patente_ingestor.agents.dto.norm_reference_describer import (
    NormReferenceDescriberResponse,
)
from guidami_ai_patente_ingestor.mappers.agents import NormReferenceDescriberMapper
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel

logger = logging.getLogger(__name__)

_DedupeKey = tuple[str, str, bool, str | None]  # (topic, text, correct_answer, image_filename)


def _make_key(q: EnrichedQuizModel) -> _DedupeKey:
    return (q.topic, q.text, q.correct_answer, q.image)


class NormReferenceEnricher(UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]]):
    """Arricchisce le sotto-domande con metadati normativi generati dall'LLM.

    La chiave di dedup è `(topic, text, correct_answer, image_filename)`: duplicati
    esatti ottengono una sola chiamata all'agente; il risultato viene propagato a tutte
    le righe che condividono la stessa chiave.
    """

    def __init__(self, agent: NormReferenceDescriberAgent) -> None:
        """Inietta l'agente LLM per la generazione di metadati normativi."""
        self._agent = agent

    def execute(self, request: list[EnrichedQuizModel]) -> list[EnrichedQuizModel]:
        """Esegue l'arricchimento normativo su ogni sotto-domanda della lista.

        Args:
            request: Lista di sotto-domande enriched da arricchire.

        Returns:
            Lista di sotto-domande con `quiz_metadata` valorizzato dove possibile.
        """
        metadata_map = self._build_metadata_map(request)
        return [self._apply_metadata(q, metadata_map) for q in request]

    def _apply_metadata(
        self,
        q: EnrichedQuizModel,
        metadata_map: dict[_DedupeKey, NormReferenceDescriberResponse],
    ) -> EnrichedQuizModel:
        key = _make_key(q)
        if key not in metadata_map:
            return q
        return NormReferenceDescriberMapper.from_response_to_enriched_quiz(q, metadata_map[key])

    def _build_metadata_map(
        self, questions: list[EnrichedQuizModel]
    ) -> dict[_DedupeKey, NormReferenceDescriberResponse]:
        seen: set[_DedupeKey] = set()
        result: dict[_DedupeKey, NormReferenceDescriberResponse] = {}
        for q in questions:
            key = _make_key(q)
            if key in seen:
                continue
            seen.add(key)
            response = self._call_agent(q)
            if response is not None:
                result[key] = response
        return result

    def _call_agent(self, q: EnrichedQuizModel) -> NormReferenceDescriberResponse | None:
        try:
            req = NormReferenceDescriberMapper.from_enriched_quiz_to_request(q)
            return self._agent.run_sync(req, images=())
        except Exception:
            logger.warning(
                "Failed to generate norm reference metadata, skipping: topic=%r text=%r",
                q.topic,
                q.text,
                exc_info=True,
            )
            return None
