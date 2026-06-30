import logging

from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.mappers.agents import ArticleContextualizerMapper
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel

logger = logging.getLogger(__name__)


class ContextEnricher:
    """Arricchisce gli articoli con i contesti per comma generati via LLM.

    Soddisfa `EnricherProtocol[EnrichedArticleModel, EnrichedArticleModel]` per struttura.
    La guard `repealed` e il mapping dominio↔DTO vivono qui, non nell'agente.
    Un fallimento isolato su un articolo non abortisce il batch: logga un warning
    e restituisce l'articolo invariato.
    """

    def __init__(self, article_contextualizer_agent: ArticleContextualizerAgent) -> None:
        """Inietta l'agente di contestualizzazione.

        Args:
            article_contextualizer_agent: Agente che genera i contesti per comma via LLM.
        """
        self._agent = article_contextualizer_agent

    def enrich(self, items: list[EnrichedArticleModel]) -> list[EnrichedArticleModel]:
        """Valorizza `contexts` su ogni articolo.

        Args:
            items: Articoli enriched (base-map) da arricchire.

        Returns:
            Nuove `EnrichedArticleModel` con `contexts` valorizzato.
        """
        return [self._contextualize(item) for item in items]

    def _contextualize(self, article: EnrichedArticleModel) -> EnrichedArticleModel:
        if article.repealed or not article.paragraphs:
            return article
        try:
            request = ArticleContextualizerMapper.from_enriched_article_to_request(article)
            response = self._agent.run_sync(request)
            return ArticleContextualizerMapper.from_response_to_enriched_article(article, response)
        except Exception:
            logger.warning(
                "Failed to contextualize article, skipping: %s", article.number, exc_info=True
            )
            return article
