from typing import Literal

from guidami_ai_patente_ingestor.models.knowledge import EmbeddableChunkModel, EnrichedArticleModel


class ArticleChunker:
    """Trasforma un `EnrichedArticleModel` in `EmbeddableChunkModel` (uno per comma).

    Valorizza `chunk.context` dai contesti inline dell'articolo enriched.
    """

    def chunk(
        self, article: EnrichedArticleModel, source: Literal["cds", "cap"]
    ) -> list[EmbeddableChunkModel]:
        """Genera i chunk di `article`: comma 0 da `text` (se non vuoto) + uno per paragrafo."""
        chunks: list[EmbeddableChunkModel] = []

        if article.text:
            chunks.append(self._build_chunk(article, source, comma_index=0, raw_text=article.text))

        for comma_index, paragraph in enumerate(article.paragraphs, start=1):
            chunks.append(
                self._build_chunk(article, source, comma_index=comma_index, raw_text=paragraph)
            )

        return chunks

    def _build_chunk(
        self,
        article: EnrichedArticleModel,
        source: Literal["cds", "cap"],
        comma_index: int,
        raw_text: str,
    ) -> EmbeddableChunkModel:
        return EmbeddableChunkModel(
            source=source,
            article_number=article.number,
            article_title=article.title,
            comma_index=comma_index,
            chunk_text=raw_text,
            context=article.contexts.get(comma_index, ""),
            is_repealed=article.repealed or "ABROGAT" in raw_text.upper(),
            source_url=article.url,
        )
