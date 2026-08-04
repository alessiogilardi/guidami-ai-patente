from guidami_ai_patente_ingestor.models.knowledge import EmbeddableArticleComma

_COMMA_REPEALED_PREFIXES = ("COMMA ABROGATO", "COMMA SOPPRESSO")


def is_comma_repealed(*, article_repealed: bool, comma_text: str) -> bool:
    """Decides whether a single comma is repealed.

    Per-comma repeal (FR-9/FR-7): a comma is repealed when its article is
    repealed, or when its own text (after stripping leading `((` markers)
    starts with `COMMA ABROGATO` or `COMMA SOPPRESSO` — comma numbers are
    already stripped from comma text by the scraper, so no separate
    number-stripping is needed here.

    Args:
        article_repealed: Whether the comma's parent article is repealed.
        comma_text: The comma's own text.

    Returns:
        `True` if the comma is repealed.
    """
    return article_repealed or comma_text.lstrip("(").strip().upper().startswith(
        _COMMA_REPEALED_PREFIXES
    )


def detect_comma_repeal(comma: EmbeddableArticleComma) -> EmbeddableArticleComma:
    """Refines `comma.is_repealed` with the per-comma text formula.

    Pipeline-step adapter around `is_comma_repealed`, meant to run in the
    `expand_to_embeddable_commas` `ApplyStep` right after the `CleanedArticleModel`
    → `EmbeddableArticleComma` expansion: at that point `comma.is_repealed` still
    holds only the article-level flag propagated by `ArticleMapper`, so it is
    read here as the "already known" input to the formula.

    Args:
        comma: Comma with `is_repealed` seeded from its parent article's flag.

    Returns:
        A copy of `comma` with `is_repealed` finalized.
    """
    return comma.model_copy(
        update={
            "is_repealed": is_comma_repealed(
                article_repealed=comma.is_repealed, comma_text=comma.text
            )
        }
    )
