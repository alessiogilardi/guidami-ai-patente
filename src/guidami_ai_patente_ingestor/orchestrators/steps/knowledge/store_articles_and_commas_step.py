"""Step that persists Article/ArticleComma records to the DB with per-source full-reload."""

import logging
from typing import cast

from flowstep import FlowContext, Step

from domain.entities.knowledge import Article, ArticleComma
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableArticleComma
from guidami_ai_patente_ingestor.repositories import (
    ArticleCommaStoreRepository,
    ArticleStoreRepository,
)

logger = logging.getLogger(__name__)

# Not yet context_keys.py constants (added in T-14): the step reads/writes them as
# hardcoded literals until then (per plan T-12).
_ARTICLE_ENTITIES_KEY = "article_entities"
_EMBEDDABLE_ARTICLE_COMMAS_KEY = "embeddable_article_commas"


class StoreArticlesAndCommasStep(Step):
    """Persists articles + commas to `articles`/`article_commas`, full-reload of that source only.

    Domain-specific: per-source delete + re-insert, resolving each comma's
    `article_id` from the DB-generated ids of the just-inserted articles
    (there is no client-side id yet, `articles.id` is `BIGSERIAL`).
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
        articles = cast(list[Article], context.get(_ARTICLE_ENTITIES_KEY))
        embeddable_commas = cast(
            list[EmbeddableArticleComma], context.get(_EMBEDDABLE_ARTICLE_COMMAS_KEY)
        )

        self._article_comma_repository.delete_source(self._source)
        self._article_repository.delete_source(self._source)

        article_ids = self._article_repository.bulk_insert_returning_ids(articles)
        id_by_number = dict(
            zip((article.number for article in articles), article_ids, strict=True)
        )

        article_commas = [
            ArticleComma(
                article_id=id_by_number[comma.article_number],
                comma_number=comma.comma_number,
                position=comma.position,
                text=comma.text,
                is_repealed=comma.is_repealed,
                embedding=comma.embedding,
            )
            for comma in embeddable_commas
        ]
        self._article_comma_repository.bulk_insert(article_commas)

        logger.info(
            f"Stored {len(articles)} articles and {len(article_commas)} commas "
            f"for source '{self._source}'"
        )

    def get_required_keys(self) -> set[str]:
        """Requires `article_entities` and `embeddable_article_commas` as input."""
        return {_ARTICLE_ENTITIES_KEY, _EMBEDDABLE_ARTICLE_COMMAS_KEY}

    def get_produced_keys(self) -> set[str]:
        """No produced key: this is the flow's terminal (sink) step."""
        return set()
