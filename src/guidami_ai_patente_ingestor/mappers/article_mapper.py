from typing import Literal

from domain.entities.knowledge import KnowledgeChunk
from guidami_ai_patente_ingestor.models.knowledge import (
    EmbeddableChunkModel,
    EnrichedArticleModel,
    ParsedArticleModel,
)


class ArticleMapper:
    """Backbone of the 1:1 transformations in the corpus normativo pipeline.

    All methods are static and pure: each maps a model to the next one in
    the chain (`from_X_to_Y`), following the same pattern as `QuizMapper`.
    """

    @staticmethod
    def from_parsed_to_enriched(article: ParsedArticleModel) -> EnrichedArticleModel:
        """Base-map: copies the common fields, `contexts` empty (populated by ContextEnricher)."""
        return EnrichedArticleModel(
            number=article.number,
            title=article.title,
            text=article.text,
            paragraphs=article.paragraphs,
            url=article.url,
            scraped_at=article.scraped_at,
            repealed=article.repealed,
            contexts={},
        )

    @staticmethod
    def from_enriched_to_embeddable_chunk(
        model: EnrichedArticleModel,
        source: Literal["cds", "cap"],
        comma_index: int,
        raw_text: str,
    ) -> EmbeddableChunkModel:
        """Creates an `EmbeddableChunkModel` from an enriched article and a specific comma.

        Args:
            model: Source enriched article.
            source: Norm source ("cds" or "cap").
            comma_index: Comma index (0 = main text).
            raw_text: Raw text of the comma to embed.

        Returns:
            Chunk ready for embedding and indexing.
        """
        return EmbeddableChunkModel(
            source=source,
            article_number=model.number,
            article_title=model.title,
            comma_index=comma_index,
            chunk_text=raw_text,
            context=model.contexts.get(comma_index, ""),
            is_repealed=model.repealed or "ABROGAT" in raw_text.upper(),
            source_url=model.url,
        )

    @staticmethod
    def from_embeddable_chunk_to_knowledge_chunk(model: EmbeddableChunkModel) -> KnowledgeChunk:
        """Maps an `EmbeddableChunkModel` to the `KnowledgeChunk` entity.

        Args:
            model: Embeddable model with embedding already computed (or `None`
                if excluded by the repealed filter).

        Returns:
            `KnowledgeChunk` entity ready for the store.
        """
        return KnowledgeChunk(
            source=model.source,
            article_number=model.article_number,
            article_title=model.article_title,
            comma_index=model.comma_index,
            chunk_text=model.chunk_text,
            context=model.context,
            is_repealed=model.is_repealed,
            source_url=model.source_url,
            embedding=model.embedding,
        )
