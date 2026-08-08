from pydantic import BaseModel


class EmbeddableArticleComma(BaseModel):
    """Intermediate model for computing the embedding of one article comma.

    One instance per comma of an article, produced from a `CleanedArticleModel`
    (`ArticleMapper.from_cleaned_to_embeddable_commas`), consumed by the
    embedding step, then mapped onto an `ArticleCommaEntity` entity for storage.
    """

    source: str
    article_number: str
    article_title: str
    comma_number: str
    position: int
    text: str
    is_repealed: bool
    embedding: list[float] | None = None
