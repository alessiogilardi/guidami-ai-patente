from typing import Literal

from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.mappers import ArticleMapper
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableChunkModel, EnrichedArticleModel


class ArticleChunker(UseCase[EnrichedArticleModel, list[EmbeddableChunkModel]]):
    """Trasforma un `EnrichedArticleModel` in `EmbeddableChunkModel` (uno per comma).

    Valorizza `chunk.context` dai contesti inline dell'articolo enriched.
    """

    def __init__(self, source: Literal["cds", "cap"]) -> None:
        """Inizializza il chunker con la sorgente normativa.

        Args:
            source: Sorgente normativa ("cds" o "cap").
        """
        self._source: Literal["cds", "cap"] = source

    def execute(self, request: EnrichedArticleModel) -> list[EmbeddableChunkModel]:
        """Genera i chunk di `article`: comma 0 da `text` (se non vuoto) + uno per paragrafo."""
        chunks: list[EmbeddableChunkModel] = []

        if request.text:
            chunks.append(
                ArticleMapper.from_enriched_to_embeddable_chunk(
                    request, self._source, comma_index=0, raw_text=request.text
                )
            )

        for comma_index, paragraph in enumerate(request.paragraphs, start=1):
            chunks.append(
                ArticleMapper.from_enriched_to_embeddable_chunk(
                    request, self._source, comma_index=comma_index, raw_text=paragraph
                )
            )

        return chunks
