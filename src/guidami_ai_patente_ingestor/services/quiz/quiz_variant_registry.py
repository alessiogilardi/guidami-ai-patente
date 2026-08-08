"""Registry of quiz query representations (AD-7).

A name, the text it embeds, and how several questions sharing that text dedup to one
embedding call (AD-8). Every variant is a declarative EmbeddingSpec composed via
FieldSpecComposer (commons.ai.embedding) — no hand-written text-joining functions.

Adding a seventh representation is exactly one QuizVariantSpec entry here plus one
name in IngestorConfig.quiz_embedding_variants — no schema change, no change to
StoreQuizStep, QuizQuestionEmbeddingStoreRepository, or the evaluation harness's arm
enumeration (which reads variant names from the database, never from this registry).
"""

from collections.abc import Mapping

from commons.ai.embedding import EmbeddingSpec, FieldSpec, FieldSpecComposer

from .quiz_variant_spec import QuizVariantSpec

# The only field depending on quiz_metadata; skip_if_none=False marks it "required" —
# when missing, it makes the whole spec's compose() return None (AD-2/FR-2: never a
# stored empty-text/null-vector row), not just drop this one field.
_search_queries_field = FieldSpec(
    extractor=lambda item: (
        item.quiz_metadata.vector_search_queries if item.quiz_metadata is not None else None
    ),
    formatter=lambda queries: "\n".join(queries),
    skip_if_none=False,
)

_text_spec = EmbeddingSpec([FieldSpec.from_attr("text")], separator="\n")

_topic_text_spec = EmbeddingSpec(
    [
        FieldSpec.from_attr("topic"),
        FieldSpec.from_attr("text"),
        FieldSpec.from_attr("image_description"),
    ],
    separator="\n",
)

_image_description_spec = EmbeddingSpec(
    [FieldSpec.from_attr("image_description", skip_if_none=False)],
    separator="\n",
)

_search_queries_spec = EmbeddingSpec([_search_queries_field], separator="\n")

_combined_spec = EmbeddingSpec(
    [FieldSpec.from_attr("topic"), FieldSpec.from_attr("text"), _search_queries_field],
    separator="\n",
)

_combined_description_spec = EmbeddingSpec(
    [
        FieldSpec.from_attr("topic"),
        FieldSpec.from_attr("text"),
        FieldSpec.from_attr("image_description"),
        _search_queries_field,
    ],
    separator="\n",
)

QUIZ_VARIANT_REGISTRY: Mapping[str, QuizVariantSpec] = {
    "text": QuizVariantSpec("text", FieldSpecComposer(_text_spec)),
    "topic_text": QuizVariantSpec("topic_text", FieldSpecComposer(_topic_text_spec)),
    "search_queries": QuizVariantSpec("search_queries", FieldSpecComposer(_search_queries_spec)),
    "combined": QuizVariantSpec("combined", FieldSpecComposer(_combined_spec)),
    "combined_description": QuizVariantSpec(
        "combined_description", FieldSpecComposer(_combined_description_spec)
    ),
    "image_description": QuizVariantSpec(
        "image_description",
        FieldSpecComposer(_image_description_spec),
        dedup_key=lambda item: item.image_filename or item.number,
    ),
}
