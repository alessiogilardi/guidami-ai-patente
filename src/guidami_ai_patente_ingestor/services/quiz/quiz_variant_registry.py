"""Registry of quiz query representations (AD-7).

A name, the text it embeds, and how several questions sharing that text dedup to one
embedding call (AD-8).

Adding a seventh representation is exactly one QuizVariantSpec entry here plus one name
in IngestorConfig.quiz_embedding_variants — no schema change, no change to StoreQuizStep,
QuizQuestionEmbeddingStoreRepository, or the evaluation harness's arm enumeration (which
reads variant names from the database, never from this registry).
"""

from collections.abc import Callable, Mapping
from typing import NamedTuple

from guidami_ai_patente_ingestor.models.quiz import EmbeddedQuizModel


class QuizVariantSpec(NamedTuple):
    """One registered representation.

    `text_builder` returns `None` when the item lacks the input this variant needs
    (FR-2: no row is written, the omission is counted). `dedup_key` groups items that
    must share one embedding call and one resulting vector (AD-8); it is only evaluated
    for items `text_builder` did not return `None` for. Defaults to `item.number` (the
    natural key — every item is already distinct, so this performs no dedup, matching
    the five per-question variants' semantics).
    """

    name: str
    text_builder: Callable[[EmbeddedQuizModel], str | None]
    dedup_key: Callable[[EmbeddedQuizModel], str] = lambda item: item.number  # noqa: E731


def _topic_text(item: EmbeddedQuizModel) -> str:
    parts = [item.topic, item.text, item.image_description]
    return "\n".join(part for part in parts if part)


def _search_queries(item: EmbeddedQuizModel) -> str | None:
    if item.quiz_metadata is None:
        return None
    return "\n".join(item.quiz_metadata.vector_search_queries)


def _combined(item: EmbeddedQuizModel) -> str | None:
    if item.quiz_metadata is None:
        return None
    return "\n".join([item.topic, item.text, *item.quiz_metadata.vector_search_queries])


def _combined_description(item: EmbeddedQuizModel) -> str | None:
    if item.quiz_metadata is None:
        return None
    parts = [item.topic, item.text, item.image_description]
    parts = [part for part in parts if part]
    return "\n".join([*parts, *item.quiz_metadata.vector_search_queries])


QUIZ_VARIANT_REGISTRY: Mapping[str, QuizVariantSpec] = {
    "text": QuizVariantSpec("text", lambda item: item.text),
    "topic_text": QuizVariantSpec("topic_text", _topic_text),
    "search_queries": QuizVariantSpec("search_queries", _search_queries),
    "combined": QuizVariantSpec("combined", _combined),
    "combined_description": QuizVariantSpec("combined_description", _combined_description),
    "image_description": QuizVariantSpec(
        "image_description",
        lambda item: item.image_description,
        dedup_key=lambda item: item.image_filename or item.number,
    ),
}
