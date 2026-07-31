import asyncio
import logging
from collections.abc import Iterable

from commons.observability import ItemProgressReporter, NullProgressReporter
from commons.use_cases import AsyncUseCase
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
    ArticleContextualizerResponse,
)
from guidami_ai_patente_ingestor.agents.mappers import ArticleContextualizerMapper
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel

logger = logging.getLogger(__name__)


class ContextEnricher(AsyncUseCase[Iterable[EnrichedArticleModel], list[EnrichedArticleModel]]):
    """Enriches articles with per-paragraph contexts generated via LLM.

    An article is skipped (returned unchanged, agent not called) when it is `repealed`
    or has neither `text` nor `paragraphs` to contextualize. The guard and the domain↔DTO
    mapping live here, not in the agent. Per-article calls run concurrently under
    `asyncio.gather`, bounded by a semaphore. An isolated failure on one article does not
    abort the batch: it logs a warning and returns the article unchanged.
    """

    def __init__(
        self,
        max_concurrency: int,
        article_contextualizer_agent: ArticleContextualizerAgent,
        progress: ItemProgressReporter | None = None,
    ) -> None:
        """Injects the concurrency limit, the contextualization agent, and an optional reporter.

        Args:
            max_concurrency: Maximum number of in-flight LLM calls per run.
            article_contextualizer_agent: Agent that generates per-paragraph contexts via LLM.
            progress: Optional port reporting one tick per completed article. When
                `None`, defaults to `NullProgressReporter`, a no-op collaborator.
        """
        # Store the limit, not the Semaphore: an asyncio.Semaphore binds to the loop of its
        # first use; the loop is owned by the caller (AsyncApplyStep), so the semaphore is
        # built per-run in `execute`, keeping the enricher reusable across runs/loops.
        self._max_concurrency = max_concurrency
        self._agent = article_contextualizer_agent
        self._progress: ItemProgressReporter = (
            progress if progress is not None else NullProgressReporter()
        )

    async def execute(self, request: Iterable[EnrichedArticleModel]) -> list[EnrichedArticleModel]:
        """Populates `contexts` on every article.

        Args:
            request: Enriched articles (base-map) to enrich.

        Returns:
            New `EnrichedArticleModel` instances with `contexts` populated where possible.
        """
        articles = list(request)
        semaphore = asyncio.Semaphore(self._max_concurrency)  # bound to this run's loop
        self._progress.begin_items("articles", len(articles))
        try:
            return list(
                await asyncio.gather(*(self._contextualize(a, semaphore) for a in articles))
            )
        finally:
            self._progress.end_items()

    async def _contextualize(
        self, article: EnrichedArticleModel, semaphore: asyncio.Semaphore
    ) -> EnrichedArticleModel:
        try:
            if article.repealed or not (article.text or article.paragraphs):
                return article
            try:
                request = ArticleContextualizerMapper.from_enriched_article_to_request(article)
                async with semaphore:
                    response: ArticleContextualizerResponse = await self._agent.run(request)
                return ArticleContextualizerMapper.from_response_to_enriched_article(
                    article, response
                )
            except Exception:
                logger.warning(
                    "Failed to contextualize article, skipping: %s", article.number, exc_info=True
                )
                return article
        finally:
            self._progress.advance_item()
