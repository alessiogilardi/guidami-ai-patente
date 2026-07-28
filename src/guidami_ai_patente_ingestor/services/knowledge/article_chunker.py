from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.mappers import ArticleMapper
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableChunkModel, EnrichedArticleModel


class ArticleChunker(UseCase[EnrichedArticleModel, list[EmbeddableChunkModel]]):
    """Transforms an `EnrichedArticleModel` into `EmbeddableChunkModel` (one per paragraph).

    Populates `chunk.context` from the enriched article's inline contexts.
    No `__init__`: the source travels with the article (Decision 17).
    """

    def execute(self, request: EnrichedArticleModel) -> list[EmbeddableChunkModel]:
        """Generates `article` chunks.

        Paragraph 0 comes from `text` (if non-empty), followed by one chunk
        per paragraph.
        """
        chunks: list[EmbeddableChunkModel] = []

        if request.text:
            chunks.append(
                ArticleMapper.from_enriched_to_embeddable_chunk(
                    request, comma_index=0, raw_text=request.text
                )
            )

        for comma_index, paragraph in enumerate(request.paragraphs, start=1):
            chunks.append(
                ArticleMapper.from_enriched_to_embeddable_chunk(
                    request, comma_index=comma_index, raw_text=paragraph
                )
            )

        return chunks
