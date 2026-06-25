from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle


class ArticleMapper:
    """Backbone delle trasformazioni 1:1 della pipeline del corpus normativo.

    Tutti i metodi sono statici e puri: ciascuno mappa un modello nel successivo
    della catena (`from_X_to_Y`), sullo stesso pattern di `QuizMapper`.
    """

    @staticmethod
    def from_article_to_enriched_article(article: Article) -> EnrichedArticle:
        """Base-map: copia i campi comuni, `contexts` vuoto (valorizzato dal ContextEnricher)."""
        return EnrichedArticle(
            number=article.number,
            title=article.title,
            text=article.text,
            paragraphs=article.paragraphs,
            url=article.url,
            scraped_at=article.scraped_at,
            repealed=article.repealed,
            contexts={},
        )
