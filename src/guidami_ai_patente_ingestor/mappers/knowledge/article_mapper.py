from commons.entities.knowledge import KnowledgeChunk
from guidami_ai_patente_ingestor.models.knowledge import (
    EmbeddableChunkModel,
    EnrichedArticleModel,
    ParsedArticleModel,
)


class ArticleMapper:
    """Backbone delle trasformazioni 1:1 della pipeline del corpus normativo.

    Tutti i metodi sono statici e puri: ciascuno mappa un modello nel successivo
    della catena (`from_X_to_Y`), sullo stesso pattern di `QuizMapper`.
    """

    @staticmethod
    def from_parsed_to_enriched(article: ParsedArticleModel) -> EnrichedArticleModel:
        """Base-map: copia i campi comuni, `contexts` vuoto (valorizzato dal ContextEnricher)."""
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
    def from_embeddable_chunk_to_knowledge_chunk(model: EmbeddableChunkModel) -> KnowledgeChunk:
        """Mappa un `EmbeddableChunkModel` nell'entità `KnowledgeChunk`.

        Args:
            model: Modello embeddable con embedding già calcolato (o `None` se
                escluso dal filtro repealed).

        Returns:
            Entità `KnowledgeChunk` pronta per lo store.
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
