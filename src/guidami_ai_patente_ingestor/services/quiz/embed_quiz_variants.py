"""Computes every enabled quiz query representation (AD-7) and embeds it.

Deduplicating by each representation's own dedup key (AD-8).
"""

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence

from commons.ai.embedding import EmbeddingService
from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.models.quiz import (
    EmbeddableQuizVariant,
    EmbeddedQuizModel,
    EmbedQuizVariantsResult,
)

from .quiz_variant_registry import QUIZ_VARIANT_REGISTRY, QuizVariantSpec

logger = logging.getLogger(__name__)


class EmbedQuizVariants(UseCase[Iterable[EmbeddedQuizModel], EmbedQuizVariantsResult]):
    """Builds and embeds every configured variant's text, one embedding-service call per variant.

    Replaces `EmbedQuizMetadata` (deleted): that class computed exactly one embedding per
    question from `quiz_metadata`; this one computes one embedding per (question,
    variant) pair, for every variant named in `enabled_variants`.
    """

    def __init__(
        self, enabled_variants: Sequence[str], embedding_service: EmbeddingService
    ) -> None:
        """Injects the enabled variant names and the embedding service.

        Raises:
            KeyError: if a name in `enabled_variants` is not in `QUIZ_VARIANT_REGISTRY` —
                a configuration typo becomes a startup error (AD-7), not a silently
                missing arm.
        """
        self._specs: list[QuizVariantSpec] = [
            QUIZ_VARIANT_REGISTRY[name] for name in enabled_variants
        ]
        self._embedding_service = embedding_service

    def execute(self, request: Iterable[EmbeddedQuizModel]) -> EmbedQuizVariantsResult:
        """Computes every enabled variant's rows and per-variant omission counts."""
        items = list(request)
        rows: list[EmbeddableQuizVariant] = []
        omitted_counts: dict[str, int] = {}
        for spec in self._specs:
            spec_rows, omitted = self._embed_variant(spec, items)
            rows.extend(spec_rows)
            omitted_counts[spec.name] = omitted
        logger.info(
            "Embedded %d quiz variant rows across %d variants", len(rows), len(self._specs)
        )
        return EmbedQuizVariantsResult(variants=rows, omitted_counts=omitted_counts)

    def _embed_variant(
        self, spec: QuizVariantSpec, items: list[EmbeddedQuizModel]
    ) -> tuple[list[EmbeddableQuizVariant], int]:
        texts_by_number = {item.number: spec.text_builder(item) for item in items}
        present = [item for item in items if texts_by_number[item.number] is not None]
        omitted = len(items) - len(present)

        groups: dict[str, list[EmbeddedQuizModel]] = defaultdict(list)
        for item in present:
            groups[spec.dedup_key(item)].append(item)

        keys = list(groups.keys())
        texts = [texts_by_number[groups[key][0].number] for key in keys]
        vectors = self._embedding_service.execute(texts) if texts else []  # type: ignore[arg-type]
        vector_by_key = dict(zip(keys, vectors, strict=True))

        rows = [
            EmbeddableQuizVariant(
                question_number=item.number, variant=spec.name, embedding=vector_by_key[key]
            )
            for key, group_items in groups.items()
            for item in group_items
        ]
        return rows, omitted
