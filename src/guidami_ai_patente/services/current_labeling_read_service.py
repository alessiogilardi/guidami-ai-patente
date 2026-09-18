"""Reads a question's current comma labeling, without ever computing one (AD-3)."""

import asyncio
import logging

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from guidami_ai_patente.exceptions import LabelingNotReadyError
from guidami_ai_patente.models import CommaSelection, CurrentLabeling
from guidami_ai_patente.providers import LabelingStackProvider
from guidami_ai_patente.repositories import GoldenSetReadRepository, QuizQuestionRepository

logger = logging.getLogger(__name__)


@service
class CurrentLabelingReadService(AsyncUseCase[str, CommaSelection]):
    """Serves the current comma association for a question, or reports its absence.

    Never retrieves and never judges (spec 0017, FR-5): this is the read-only half
    of what `CommaSelectorService` used to do alone, extracted so `ExplanationService`
    depends on a component that structurally cannot trigger the judge (AD-3). The
    hit-branch logic (`find_current_labeling` + comma read) is exactly
    `CommaSelectorService`'s former `_selection_for`, moved here so both it and
    `ExplanationService` share one implementation instead of two.

    Distinguishes two shapes of "no current labeling" (AD-4), mirroring
    `ExplanationStatusService`'s own classification: no embedding at all is a
    permanent pipeline gap (`CommaSelection(labeling=None)`, read by
    `ExplanationService` as `not_indexed`); an embedding with no labeling means the
    caller skipped `POST /label` — a contract violation (`LabelingNotReadyError`,
    409). `CommaSelectorService` (Task 3) turns that same exception into "go label
    it live," which is why it is not merely an internal detail.
    """

    judge_identity: Autowired[LabelingStackProvider]
    golden_set: Autowired[GoldenSetReadRepository]
    questions: Autowired[QuizQuestionRepository]

    async def execute(self, number: str) -> CommaSelection:
        """Returns the current selection for `number`, or raises if never labeled.

        Args:
            number: The question's `number`.

        Raises:
            LabelingNotReadyError: The question is embedded but has no current
                labeling — the caller should have called `POST /label` first.
        """
        epoch = self.judge_identity.epoch
        current = await asyncio.to_thread(self.golden_set.find_current_labeling, number, epoch)
        if current is not None:
            return await self._selection_for(current)

        embedded = await asyncio.to_thread(
            self.questions.has_embedding, number, epoch.candidate_variant
        )
        if embedded:
            raise LabelingNotReadyError(number)
        return CommaSelection(labeling=None)

    async def _selection_for(self, current: CurrentLabeling) -> CommaSelection:
        """Reads a current labeling's commas, or reports its empty verdict."""
        if not current.has_supporting_commas:
            return CommaSelection(labeling=current)

        commas = await asyncio.to_thread(self.golden_set.find_labeled_commas, current.id)
        if not commas:
            logger.warning(
                "Labeling %d has has_supporting_commas=true but no comma rows: a corpus "
                "delete cascaded them away (AD-10's detection hole)",
                current.id,
            )
        return CommaSelection(labeling=current, commas=tuple(commas))
