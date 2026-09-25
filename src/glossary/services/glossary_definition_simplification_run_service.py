import logging
from itertools import batched

import psycopg
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from glossary.configs import GlossaryConfig
from glossary.exceptions import GlossaryDefinitionSimplificationError
from glossary.models import (
    GlossaryDefinitionSimplificationReport,
    GlossaryDefinitionSimplificationRequest,
    SimplifiedDefinition,
)
from glossary.repositories import (
    GlossaryDefinitionReadRepository,
    GlossaryDefinitionUpdateRepository,
)

from .glossary_definition_simplification_service import GlossaryDefinitionSimplificationService

logger = logging.getLogger(__name__)

# Mirrors GlossaryTermTranslationRunService's _ISOLATED_BATCH_FAILURES: only the
# runtime failure modes a batch can actually hit are isolated here — anything else is
# a programming bug and must propagate.
_ISOLATED_BATCH_FAILURES = (
    psycopg.Error,
    ModelHTTPError,
    UnexpectedModelBehavior,
    ValidationError,
)


@service
class GlossaryDefinitionSimplificationRunService(
    AsyncUseCase[GlossaryDefinitionSimplificationRequest, GlossaryDefinitionSimplificationReport]
):
    """Sequences `simplify-glossary-definitions`: read, batch, simplify, write (FR-2).

    Mirrors `GlossaryTermTranslationRunService`'s role for the term-translation script,
    with the same failure-isolation shape at the batch level.
    """

    config: Autowired[GlossaryConfig]
    read_repository: Autowired[GlossaryDefinitionReadRepository]
    update_repository: Autowired[GlossaryDefinitionUpdateRepository]
    simplification_service: Autowired[GlossaryDefinitionSimplificationService]

    async def execute(
        self, request: GlossaryDefinitionSimplificationRequest
    ) -> GlossaryDefinitionSimplificationReport:
        """Simplifies every batch, isolating a failing batch's read+write from its siblings."""
        rows = self.read_repository.find_missing_simplifications(request.force)
        simplified = 0
        failed_ids: list[int] = []
        for batch in batched(rows, self.config.simplification_batch_size):
            batch = list(batch)
            try:
                simplifications: list[SimplifiedDefinition] = await self.simplification_service(
                    batch
                )
                self.update_repository.update_many(
                    [
                        (row.id, s.definition_plain)
                        for row, s in zip(batch, simplifications, strict=True)
                    ]
                )
                simplified += len(batch)
            except _ISOLATED_BATCH_FAILURES:
                ids = [row.id for row in batch]
                logger.exception("Simplification batch failed for definition ids %s", ids)
                failed_ids.extend(ids)

        if failed_ids:
            raise GlossaryDefinitionSimplificationError(failed_ids)

        still_missing = len(self.read_repository.find_missing_simplifications(force=False))
        return GlossaryDefinitionSimplificationReport(
            simplified=simplified, still_missing=still_missing
        )
