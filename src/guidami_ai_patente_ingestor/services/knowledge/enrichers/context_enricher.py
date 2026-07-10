import logging
from collections.abc import Iterable

from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.mappers.agents import ArticleContextualizerMapper
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel

logger = logging.getLogger(__name__)


class ContextEnricher(UseCase[Iterable[EnrichedArticleModel], list[EnrichedArticleModel]]):
    """Enriches articles with per-paragraph contexts generated via LLM.

    The `repealed` guard and the domain↔DTO mapping live here, not in the agent.
    An isolated failure on one article does not abort the batch: it logs a warning
    and returns the article unchanged.
    """

    def __init__(self, article_contextualizer_agent: ArticleContextualizerAgent) -> None:
        """Injects the contextualization agent.

        Args:
            article_contextualizer_agent: Agent that generates per-paragraph contexts via LLM.
        """
        self._agent = article_contextualizer_agent

    def execute(self, request: Iterable[EnrichedArticleModel]) -> list[EnrichedArticleModel]:
        """Populates `contexts` on every article.

        Args:
            request: Enriched articles (base-map) to enrich.

        Returns:
            New `EnrichedArticleModel` instances with `contexts` populated.
        """
        return [self._contextualize(item) for item in request]

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
