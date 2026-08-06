"""Persists ArticleEntity/ArticleCommaEntity records to the DB via upsert + reconciliation."""

import logging
from typing import cast

from flowstep import FlowContext, Step

from domain.entities.knowledge import ArticleEntity
from guidami_ai_patente_ingestor.mappers import ArticleMapper
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableArticleComma
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import (
    ArticleCommaStoreRepository,
    ArticleStoreRepository,
)

logger = logging.getLogger(__name__)


class StoreArticlesAndCommasStep(Step):
    """Persists articles + commas to `articles`/`article_commas` via upsert on the natural key.

    Domain-specific: articles are upserted on `(source, number)` and commas on
    `(article_id, comma_number)`, so a row's `id` stays stable across runs — the
    same reason `article_id` is resolved from the DB-generated ids of the just-
    upserted articles rather than assumed (there is no client-side id yet,
    `articles.id` is `BIGSERIAL`). Each upsert is paired with a reconciling delete
    scoped to `self._source`, so a natural key no longer present in this run's
    input is removed. Only `articles` is explicitly reconciled: a removed
    article's commas go with it via `article_commas.article_id`'s
    `ON DELETE CASCADE`, so the comma reconciliation only needs to catch commas
    whose parent article survived but whose own key did not.
    """

    def __init__(
        self,
        name: str,
        source: str,
        article_repository: ArticleStoreRepository,
        article_comma_repository: ArticleCommaStoreRepository,
    ) -> None:
        """Injects the run's source and the two store repositories.

        Args:
            name: Unique step name within the flow.
            source: Source this run's upsert + reconciliation is scoped to.
            article_repository: Write repository for `articles`.
            article_comma_repository: Write repository for `article_commas`.
        """
        super().__init__(name)
        self._source = source
        self._article_repository = article_repository
        self._article_comma_repository = article_comma_repository

    def execute(self, context: FlowContext) -> None:
        """Upserts articles + commas, then reconciles both away from what vanished.

        Args:
            context: Shared pipeline context.
        """
        articles = cast(list[ArticleEntity], context.get(context_keys.ARTICLE_ENTITIES))
        embeddable_commas = cast(
            list[EmbeddableArticleComma], context.get(context_keys.EMBEDDABLE_ARTICLE_COMMAS)
        )

        logger.debug("Upserting %d articles for source %r", len(articles), self._source)

        article_ids = self._article_repository.upsert_returning_ids(articles)
        article_id_by_number = dict(
            zip((article.number for article in articles), article_ids, strict=True)
        )
        self._article_repository.delete_missing(self._source, articles)  # cascades to commas

        article_commas = [
            ArticleMapper.from_embeddable_comma_to_article_comma(comma, article_id_by_number)
            for comma in embeddable_commas
        ]
        self._article_comma_repository.upsert(article_commas)
        self._article_comma_repository.delete_missing(article_ids, article_commas)

        logger.info(
            "Upserted %d articles and %d commas for source %r",
            len(articles),
            len(article_commas),
            self._source,
        )

    def get_required_keys(self) -> set[str]:
        """Requires `ARTICLE_ENTITIES` and `EMBEDDABLE_ARTICLE_COMMAS` as input."""
        return {context_keys.ARTICLE_ENTITIES, context_keys.EMBEDDABLE_ARTICLE_COMMAS}

    def get_produced_keys(self) -> set[str]:
        """No produced key: this is the flow's terminal (sink) step."""
        return set()
