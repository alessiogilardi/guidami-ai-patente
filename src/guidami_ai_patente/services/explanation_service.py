"""Renders a grounded explanation, or reports why the corpus cannot justify one."""

import asyncio
import logging

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from guidami_ai_patente.agents import ExplanationWriterAgent
from guidami_ai_patente.agents.explanation_writer.dto import (
    ExplanationWriterRequest,
    ExplanationWriterResponse,
)
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.enums import ExplanationResult, InsufficientKnowledgeReason
from guidami_ai_patente.exceptions import ExplanationUnavailableError, QuestionNotFoundError
from guidami_ai_patente.models import (
    CommaSelection,
    Explanation,
    ExplanationRequest,
    QuestionContext,
)
from guidami_ai_patente.repositories import QuizQuestionRepository

from .current_labeling_read_service import CurrentLabelingReadService

logger = logging.getLogger(__name__)

# Attempts at a grounded citation list before giving up (FR-10). The response model
# already rejects an empty or repeated list, which pydantic-ai retries on its own; this
# covers the one failure it cannot see, an ordinal outside the supplied commas.
_CITATION_ATTEMPTS = 3


@service
class ExplanationService(AsyncUseCase[ExplanationRequest, Explanation]):
    """Turns a comma selection into prose, or into an honest refusal (FR-5, FR-7).

    The request runs under `AppConfig.explanation_deadline_s`, which — since spec
    0017 moved retrieval and the judge to `POST /label` (`LabelingService`) — now
    covers only the writer stage: `reader` (`CurrentLabelingReadService`) never
    retrieves and never judges, so its own cost is a handful of indexed reads. The
    deadline is deliberately not a lower `timeout` in `comma_labeler.yaml` either
    way: that file is the batch's own, shared and untouched by this service.

    `asyncio.timeout` cancels the inner work, which surfaces as `CancelledError` — a
    `BaseException`, so nothing in the writer's `except Exception` (`_call_writer`)
    can swallow it — and re-raises `TimeoutError` here, which becomes FR-13's 503.

    The budget bounds the `await`ed work, not a `to_thread` call already running: an
    executor thread cannot be interrupted, so a cancellation lands only when it
    returns. That is why the budget is sized against the judge (~10s, awaited and
    genuinely cancellable) and not against the threaded SQL, which is
    millisecond-scale. Do not treat this as a bug to fix — a reader who assumes the
    budget also strictly bounds SQL latency will size it wrongly the first time a
    query gets slow.

    The writer is never invoked without supporting commas (FR-7). It *is* a container
    singleton, so it exists whether or not a given request calls it; what the endpoint
    guarantees is that a refusal issues no call, which is what the unit test counts.

    FR-10's grounding is enforced here rather than in the response model, which cannot
    see how many commas were supplied: an ordinal outside the set is retried, and
    exhausting `_CITATION_ATTEMPTS` is a 503, not a fabricated citation.
    """

    config: Autowired[AppConfig]
    questions: Autowired[QuizQuestionRepository]
    reader: Autowired[CurrentLabelingReadService]
    writer: Autowired[ExplanationWriterAgent]

    async def execute(self, request: ExplanationRequest) -> Explanation:
        """Explains `request.number`, or reports why it cannot be explained.

        Raises:
            QuestionNotFoundError: No question carries that number (404).
            LabelingNotReadyError: The question is embedded but has no current
                labeling (409) — the caller should call POST /{number}/label first.
            ExplanationUnavailableError: The writer failed, or the request exceeded
                its deadline (503, FR-13).
        """
        context = await asyncio.to_thread(self.questions.find_question_context, request.number)
        if context is None:
            raise QuestionNotFoundError(request.number)

        try:
            async with asyncio.timeout(self.config.explanation_deadline_s):
                return await self._explain(request, context)
        except TimeoutError as error:
            logger.warning(
                "Explanation for quiz %s exceeded its %.1fs budget",
                request.number,
                self.config.explanation_deadline_s,
            )
            raise ExplanationUnavailableError(
                f"the explanation for question {request.number} exceeded the "
                f"{self.config.explanation_deadline_s:.0f}s budget"
            ) from error

    async def _explain(self, request: ExplanationRequest, context: QuestionContext) -> Explanation:
        """Selects the commas, then renders them or refuses."""
        selection = await self.reader(request.number)
        if not selection.commas:
            return self._insufficient(selection)

        response = await self._call_writer(
            ExplanationWriterRequest(
                quiz_text=context.text,
                correct_answer=context.correct_answer,
                commas=list(selection.commas),
                image_description=context.image_description,
                submitted_answer=request.submitted,
            ),
            request.number,
        )
        logger.info(
            "Explained quiz %s from %d comma(s) (labeling %s)",
            request.number,
            len(selection.commas),
            selection.labeling.id if selection.labeling is not None else "?",
        )
        return Explanation(
            result=ExplanationResult.EXPLAINED,
            explanation=response.explanation,
            citations=selection.commas,
            provenance=selection.labeling,
        )

    async def _call_writer(
        self, writer_request: ExplanationWriterRequest, number: str
    ) -> ExplanationWriterResponse:
        """Calls the writer until its citations are grounded (FR-10, AD-14).

        Raises:
            ExplanationUnavailableError: The writer raised, or kept citing an ordinal
                outside the supplied commas.
        """
        supplied = len(writer_request.commas)
        for attempt in range(_CITATION_ATTEMPTS):
            try:
                response = await self.writer.run(writer_request)
            except Exception as error:
                logger.warning("Explanation writer failed for quiz %s", number, exc_info=True)
                raise ExplanationUnavailableError(
                    f"the explanation writer failed for question {number}"
                ) from error

            if all(1 <= ordinal <= supplied for ordinal in response.cited_comma_numbers):
                return response

            logger.warning(
                "Writer cited %r, outside the %d supplied commas for quiz %s (attempt %d/%d)",
                response.cited_comma_numbers,
                supplied,
                number,
                attempt + 1,
                _CITATION_ATTEMPTS,
            )

        raise ExplanationUnavailableError(
            f"the explanation writer kept citing a comma it was not given for question {number}"
        )

    @staticmethod
    def _insufficient(selection: CommaSelection) -> Explanation:
        """Maps the absence of commas onto FR-7's closed reason vocabulary (AD-6).

        `not_indexed` is kept rigorously separate from the two corpus-gap values: it is
        a **pipeline** gap that re-running ingestion fixes, while `no_supporting_norm`
        is a **corpus** gap no re-run fixes. Collapsing them would hide pipeline
        regressions permanently.
        """
        if selection.labeling is None:
            return Explanation(
                result=ExplanationResult.INSUFFICIENT_KNOWLEDGE,
                reason=InsufficientKnowledgeReason.NOT_INDEXED,
            )

        reason = (
            InsufficientKnowledgeReason.NO_SUPPORTING_NORM_CONFIRMED
            if selection.labeling.human_validated
            else InsufficientKnowledgeReason.NO_SUPPORTING_NORM
        )
        return Explanation(
            result=ExplanationResult.INSUFFICIENT_KNOWLEDGE,
            reason=reason,
            judge_rationale=selection.labeling.rationale,
            provenance=selection.labeling,
        )
