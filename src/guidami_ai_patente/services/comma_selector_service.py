"""Resolves a question to the commas that ground its explanation (FR-5, FR-6)."""

import asyncio
import logging

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from domain.enums import LabelingRunOrigin
from guidami_ai_patente.exceptions import ExplanationUnavailableError, LabelingNotReadyError
from guidami_ai_patente.models import CommaSelection
from guidami_ai_patente.providers import LabelingStackProvider, LiveLabelingStackProvider
from labeling import EMBEDDING_MODEL_COLUMN
from labeling.configs import LabelingConfig
from labeling.mappers import LabelingRunMapper
from labeling.models import LabelingEpoch, QuestionLabelingRequest

from .current_labeling_read_service import CurrentLabelingReadService

logger = logging.getLogger(__name__)


@service
class CommaSelectorService(AsyncUseCase[str, CommaSelection]):
    """Serves the cached comma association, or computes it live and writes it through.

    On a hit (FR-5) `reader` — `CurrentLabelingReadService` — answers directly, no
    retrieval query and no judge call, the property the endpoint's whole cost model
    rests on. `reader` raising `LabelingNotReadyError` is this service's *own* signal
    to compute live (FR-6): reads the precomputed query vector for the epoch's
    variant and delegates to the shared `QuestionLabelingService`, the same unit the
    batch pass runs, so a live labeling and a batch labeling under one epoch key are
    genuinely interchangeable (AD-12). `reader`'s own `not_indexed` result (no
    embedding at all) is returned as-is: there is nothing to compute from.

    Nothing is embedded at request time: `quiz_question_embeddings` already holds the
    vector for the configured variant, and recomputing it would add an embedding client
    and ~200ms for a byte-identical result (AD-13).

    The labeling is re-read (via `reader`, so its comma-loading logic is not
    duplicated here) rather than reconstructed from the id the unit returns: the
    provenance block needs `rationale`, `origin`, `judge_model` and
    `human_validated`, and re-reading gives the race's winner and its loser one code
    path (AD-19) while proving FR-8's precedence agrees with what was just written.
    If that re-read still finds nothing labeled, that is the pre-existing "written
    labeling not readable back" anomaly, not a second miss — spelled out as
    `ExplanationUnavailableError`, never as a second live-labeling attempt.

    Every failure of the judge stage becomes `ExplanationUnavailableError`, and by
    construction leaves no golden-set row: the run id is resolved inside the shared
    unit only after the judge answers (AD-20, FR-13). `asyncio.CancelledError` is
    deliberately not caught — `LabelingService`'s deadline needs it to propagate
    (spec 0017, AD-10).
    """

    labeling_config: Autowired[LabelingConfig]
    judge_identity: Autowired[LabelingStackProvider]
    live_stack: Autowired[LiveLabelingStackProvider]
    reader: Autowired[CurrentLabelingReadService]

    async def execute(self, number: str) -> CommaSelection:
        """Returns the commas grounding a question's explanation, computing them if needed.

        Args:
            number: The question's `number`.

        Raises:
            ExplanationUnavailableError: The live stage failed, or its written labeling
                cannot be read back (FR-13).
        """
        epoch = self.judge_identity.epoch
        try:
            return await self.reader(number)
        except LabelingNotReadyError:
            return await self._label_live(number, epoch)

    async def _label_live(self, number: str, epoch: LabelingEpoch) -> CommaSelection:
        """Runs the shared labeling unit for one question and serves the result."""
        row = await asyncio.to_thread(
            self.live_stack.quiz.find_with_vector,
            number,
            epoch.candidate_variant,
            EMBEDDING_MODEL_COLUMN,
        )
        if row is None:
            logger.info(
                "No query vector for quiz %s under variant %r: not indexed",
                number,
                epoch.candidate_variant,
            )
            return CommaSelection(labeling=None)

        logger.debug("Cache miss for quiz %s; labeling live under epoch %r", number, epoch)
        try:
            labeling_id = await self.live_stack.question_labeling(
                QuestionLabelingRequest(row=row, resolve_run_id=lambda: self._live_run_id(epoch))
            )
        except Exception as error:
            logger.warning("Live labeling failed for quiz %s", number, exc_info=True)
            raise ExplanationUnavailableError(
                f"the labeling pipeline failed for question {number}"
            ) from error

        if labeling_id is None:
            logger.debug("Another request labeled quiz %s first; reading its labeling", number)

        try:
            return await self.reader(number)
        except LabelingNotReadyError as error:
            raise ExplanationUnavailableError(
                f"the labeling just written for question {number} is not readable back"
            ) from error

    def _live_run_id(self, epoch: LabelingEpoch) -> int:
        """Creates or reuses the one live run for this epoch (FR-9).

        Synchronous on purpose: it is invoked by the shared unit from inside its own
        `asyncio.to_thread`, right before the labeling insert.
        """
        return self.live_stack.golden_set.find_or_create_live_run(
            LabelingRunMapper.from_epoch_to_entity(
                epoch,
                LabelingRunOrigin.LIVE,
                shuffle_seed=self.labeling_config.shuffle_seed,
                corpus_comma_count=self.live_stack.corpus.comma_count(),
            )
        )
