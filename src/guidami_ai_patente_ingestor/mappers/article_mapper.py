from typing import Literal

from domain.entities.knowledge import Article
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
        article: ParsedArticleModel, source: Literal["cds", "cap"]
    ) -> CleanedArticleModel:
        """Stamp the source onto a cleaned article.

        `source` enters the data here, at the parsed→cleaned boundary, where the
        flow knows which source it is processing.
        """
        return CleanedArticleModel(**article.model_dump(), source=source)

    @staticmethod
    def from_cleaned_to_article_entity(article: CleanedArticleModel) -> Article:
        """Maps a `CleanedArticleModel` onto the insertable `Article` entity.

        Args:
            article: Cleaned article to map.

        Returns:
            `Article` entity ready for `ArticleStoreRepository`.
        """
        return Article(
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
