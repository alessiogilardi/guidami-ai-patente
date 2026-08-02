from typing import Literal

from domain.entities.knowledge import ArticleCommaEntity, ArticleEntity
from guidami_ai_patente_ingestor.models.knowledge import (
    CleanedArticleModel,
    EmbeddableArticleComma,
    ParsedArticleModel,
)

_COMMA_REPEALED_PREFIX = "COMMA ABROGATO"


class ArticleMapper:
    """Backbone of the 1:1 transformations in the corpus normativo pipeline.

    All methods are static and pure: each maps a model to the next one in
    the chain (`from_X_to_Y`), following the same pattern as `QuizMapper`.
    """

    @staticmethod
    def from_parsed_to_cleaned(
        article: ParsedArticleModel, source: Literal["cds", "cap", "reg"]
    ) -> CleanedArticleModel:
        """Stamp the source onto a cleaned article.

        `source` enters the data here, at the parsed→cleaned boundary, where the
        flow knows which source it is processing.
        """
        return CleanedArticleModel(**article.model_dump(), source=source)

    @staticmethod
    def from_cleaned_to_article_entity(article: CleanedArticleModel) -> ArticleEntity:
        """Maps a `CleanedArticleModel` onto the insertable `ArticleEntity` entity.

        Args:
            article: Cleaned article to map.

        Returns:
            `ArticleEntity` entity ready for `ArticleStoreRepository`.
        """
        return ArticleEntity(
            source=article.source,
            number=article.number,
            title=article.title,
            url=article.url,
            is_repealed=article.repealed,
        )

    @staticmethod
    def from_cleaned_to_embeddable_commas(
        article: CleanedArticleModel,
    ) -> list[EmbeddableArticleComma]:
        """Expands a `CleanedArticleModel` into one `EmbeddableArticleComma` per comma.

        Per-comma repeal (FR-9): a comma is repealed when its article is repealed,
        or when its own text (after stripping leading `((` markers) starts with
        `COMMA ABROGATO` — comma numbers are already stripped from comma text by
        the scraper, so no separate number-stripping is needed here.

        Args:
            article: Cleaned article to expand.

        Returns:
            One `EmbeddableArticleComma` per comma, in the article's comma order,
            with `embedding=None` (computed later by `EmbedCommasStep`).
        """
        return [
            EmbeddableArticleComma(
                source=article.source,
                article_number=article.number,
                article_title=article.title,
                comma_number=comma.number,
                position=position,
                text=comma.text,
                is_repealed=article.repealed
                or comma.text.lstrip("(").strip().upper().startswith(_COMMA_REPEALED_PREFIX),
                embedding=None,
            )
            for position, comma in enumerate(article.commas)
        ]

    @staticmethod
    def from_embeddable_comma_to_article_comma(
        comma: EmbeddableArticleComma, article_id_by_number: dict[str, int]
    ) -> ArticleCommaEntity:
        """Resolves the comma's DB-generated `article_id` and maps it onto the insertable entity.

        Args:
            comma: Embeddable comma, still referencing its parent by `article_number`.
            article_id_by_number: `ArticleEntity.number` -> DB-generated id, from the
                just-inserted articles.

        Returns:
            `ArticleCommaEntity` entity ready for `ArticleCommaStoreRepository`.
        """
        return ArticleCommaEntity(
            article_id=article_id_by_number[comma.article_number],
            comma_number=comma.comma_number,
            position=comma.position,
            text=comma.text,
            is_repealed=comma.is_repealed,
            embedding=comma.embedding,
        )
