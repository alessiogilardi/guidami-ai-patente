"""Persists ArticleEntity/ArticleCommaEntity records to the DB, per-source full-reload."""

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
    """Persists articles + commas to `articles`/`article_commas`, full-reload of that source only.

    Domain-specific: per-source delete + re-insert, resolving each comma's
    `article_id` from the DB-generated ids of the just-inserted articles
    (there is no client-side id yet, `articles.id` is `BIGSERIAL`). Only the
    articles are explicitly deleted: `article_commas.article_id` is
    `ON DELETE CASCADE`, so deleting a source's articles already removes its commas.
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
            source: Source whose content must be replaced (delete-by-source + insert).
            article_repository: Write repository for `articles`.
            article_comma_repository: Write repository for `article_commas`.
        """
        super().__init__(name)
        self._source = source
        self._article_repository = article_repository
        self._article_comma_repository = article_comma_repository

    def execute(self, context: FlowContext) -> None:
        """Reads articles + commas, deletes the source's rows, and re-inserts them.

        Args:
            context: Shared pipeline context.
        """
        articles = cast(list[ArticleEntity], context.get(context_keys.ARTICLE_ENTITIES))
        embeddable_commas = cast(
            list[EmbeddableArticleComma], context.get(context_keys.EMBEDDABLE_ARTICLE_COMMAS)
        )

        self._article_repository.delete_source(self._source)  # cascades to article_commas

        article_ids = self._article_repository.bulk_insert_returning_ids(articles)
        article_id_by_number = dict(
            zip((article.number for article in articles), article_ids, strict=True)
        )

        article_commas = [
            ArticleMapper.from_embeddable_comma_to_article_comma(comma, article_id_by_number)
            for comma in embeddable_commas
        ]
        self._article_comma_repository.bulk_insert(article_commas)

        logger.info(
            "Stored %d articles and %d commas for source %r",
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
