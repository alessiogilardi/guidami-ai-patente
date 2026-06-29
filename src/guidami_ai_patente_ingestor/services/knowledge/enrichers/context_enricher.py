import logging

from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel

logger = logging.getLogger(__name__)


class ContextEnricher:
    """Arricchisce gli articoli con i contesti per comma generati via LLM.

    Soddisfa `EnricherProtocol[EnrichedArticleModel, EnrichedArticleModel]` per struttura.
    Un fallimento isolato dell'agente su un articolo non abort l'intero batch:
    logga un warning e produce `contexts={}` per quell'articolo, mirror esatto
    della tolleranza ai fallimenti di `ImageDescriptionEnricher._describe_images`.
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
        return [item.model_copy(update={"contexts": self._contextualize(item)}) for item in items]

    def _contextualize(self, article: EnrichedArticleModel) -> dict[int, str]:
        try:
            return self._agent.contextualize(article)
        except Exception:
            logger.warning(
                f"Failed to contextualize article, skipping: {article.number}", exc_info=True
            )
            return {}
