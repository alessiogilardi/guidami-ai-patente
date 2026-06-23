from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle


class EnrichedArticleMapper:
    """Converte `Article` in `EnrichedArticle` (layer enriched).

    Copia i campi comuni e imposta `contexts` con i contesti per comma
    generati dall'agente di contestualizzazione.
    """

    @staticmethod
    def from_article_to_enriched_article(
        article: Article, contexts: dict[int, str]
    ) -> EnrichedArticle:
        """Mappa un `Article` + contesti per comma in `EnrichedArticle`."""
        return EnrichedArticle(
            number=article.number,
            title=article.title,
            text=article.text,
            paragraphs=article.paragraphs,
            url=article.url,
            scraped_at=article.scraped_at,
            repealed=article.repealed,
            contexts=contexts,
        )
