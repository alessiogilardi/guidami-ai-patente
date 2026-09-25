import logging
from itertools import batched

import psycopg
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from glossary.configs import GlossaryConfig
from glossary.exceptions import GlossaryTranslationError
from glossary.models import (
    GlossaryTermTranslationReport,
    GlossaryTermTranslationRequest,
    TranslatedTerm,
)
from glossary.repositories import GlossaryTermReadRepository, GlossaryTermUpdateRepository

from .glossary_term_translation_service import GlossaryTermTranslationService

logger = logging.getLogger(__name__)

# Mirrors GlossaryBuildService's _ISOLATED_BLOCK_FAILURES (Task 9): only the runtime
# failure modes a batch can actually hit are isolated here — anything else is a
# programming bug and must propagate.
_ISOLATED_BATCH_FAILURES = (
    psycopg.Error,
    ModelHTTPError,
    UnexpectedModelBehavior,
    ValidationError,
)


@service
class GlossaryTermTranslationRunService(
    AsyncUseCase[GlossaryTermTranslationRequest, GlossaryTermTranslationReport]
):
    """Sequences `translate-glossary-terms`: read, batch, translate, write (FR-5).

    Mirrors `GlossaryBuildService`'s role for the other script, with the same
    failure-isolation shape at the batch level instead of the block level.
    """

    config: Autowired[GlossaryConfig]
    read_repository: Autowired[GlossaryTermReadRepository]
    update_repository: Autowired[GlossaryTermUpdateRepository]
    translation_service: Autowired[GlossaryTermTranslationService]

    async def execute(
        self, request: GlossaryTermTranslationRequest
    ) -> GlossaryTermTranslationReport:
        """Translates every batch, isolating a failing batch's read+write from its siblings."""
        rows = self.read_repository.find_missing_translations(request.force)
        translated = 0
        failed_ids: list[int] = []
        for batch in batched(rows, self.config.translation_batch_size):
            batch = list(batch)
            try:
                translations: list[TranslatedTerm] = await self.translation_service(batch)
                self.update_repository.update_many(
                    [(row.id, t.term_ru) for row, t in zip(batch, translations, strict=True)]
                )
                translated += len(batch)
            except _ISOLATED_BATCH_FAILURES:
                ids = [row.id for row in batch]
                logger.exception("Translation batch failed for term ids %s", ids)
                failed_ids.extend(ids)

        if failed_ids:
            raise GlossaryTranslationError(failed_ids)

        still_missing = len(self.read_repository.find_missing_translations(force=False))
        return GlossaryTermTranslationReport(translated=translated, still_missing=still_missing)
