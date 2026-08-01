from pydantic import BaseModel


class EmbeddableArticleComma(BaseModel):
    """Intermediate model for computing the embedding of one article comma.

    One instance per comma of an article, produced from a `CleanedArticleModel`
    (`ArticleMapper.from_cleaned_to_embeddable_commas`), consumed by the
    embedding step, then mapped onto an `ArticleComma` entity for storage.
    """

    source: str
    article_number: str
    article_title: str
    comma_number: str
    position: int
    text: str
    is_repealed: bool
    embedding: list[float] | None = None

    @property
    def embedded_text(self) -> str:
        """Text used for computing the embedding.

        Concatenates title and comma text, one part per line, discarding
        empty parts — no context (AD-18: the LLM enrichment step is gone).
        """
        parts = [self.article_title, self.text]
        return "\n".join(part for part in parts if part)
