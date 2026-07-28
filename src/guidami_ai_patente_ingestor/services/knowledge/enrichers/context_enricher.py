import asyncio
import logging
from collections.abc import Iterable

from commons.use_cases import AsyncUseCase
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
    ArticleContextualizerResponse,
)
from guidami_ai_patente_ingestor.mappers.agents import ArticleContextualizerMapper
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel

logger = logging.getLogger(__name__)


class ContextEnricher(AsyncUseCase[Iterable[EnrichedArticleModel], list[EnrichedArticleModel]]):
    """Enriches articles with per-paragraph contexts generated via LLM.

    The `repealed`/`paragraphs` guard and the domain↔DTO mapping live here, not in the
    agent. Per-article calls run concurrently under `asyncio.gather`, bounded by a
    semaphore. An isolated failure on one article does not abort the batch: it logs a
    warning and returns the article unchanged.
    """

    def __init__(
        self, max_concurrency: int, article_contextualizer_agent: ArticleContextualizerAgent
    ) -> None:
        """Injects the concurrency limit and the contextualization agent.

        Args:
            max_concurrency: Maximum number of in-flight LLM calls per run.
            article_contextualizer_agent: Agent that generates per-paragraph contexts via LLM.
        """
        # Store the limit, not the Semaphore: an asyncio.Semaphore binds to the loop of its
        # first use; the loop is owned by the caller (AsyncApplyStep), so the semaphore is
        # built per-run in `execute`, keeping the enricher reusable across runs/loops.
        self._max_concurrency = max_concurrency
        self._agent = article_contextualizer_agent

    async def execute(self, request: Iterable[EnrichedArticleModel]) -> list[EnrichedArticleModel]:
        """Populates `contexts` on every article.

        Args:
            request: Enriched articles (base-map) to enrich.

        Returns:
            New `EnrichedArticleModel` instances with `contexts` populated where possible.
        """
        articles = list(request)
        semaphore = asyncio.Semaphore(self._max_concurrency)  # bound to this run's loop
        return list(await asyncio.gather(*(self._contextualize(a, semaphore) for a in articles)))

    async def _contextualize(
        self, article: EnrichedArticleModel, semaphore: asyncio.Semaphore
    ) -> EnrichedArticleModel:
        if article.repealed or not article.paragraphs:
            return article
        try:
            request = ArticleContextualizerMapper.from_enriched_article_to_request(article)
            async with semaphore:
                response: ArticleContextualizerResponse = await self._agent.run(request)
            return ArticleContextualizerMapper.from_response_to_enriched_article(article, response)
        except Exception:
            logger.warning(
                "Failed to contextualize article, skipping: %s", article.number, exc_info=True
            )
            return article
