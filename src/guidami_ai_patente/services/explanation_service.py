"""Renders a grounded explanation, or reports why the corpus cannot justify one."""

import asyncio
import logging
import random

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from guidami_ai_patente.agents import (
    ExplanationWriterAgent,
    GlossaryEnricherAgent,
    QuestionExplainerAgent,
)
from guidami_ai_patente.agents.explanation_writer.dto import (
    ExplanationWriterRequest,
    ExplanationWriterResponse,
)
from guidami_ai_patente.agents.glossary_enricher.dto import GlossaryEnricherRequest
from guidami_ai_patente.agents.question_explainer.dto import QuestionExplainerRequest
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.enums import ExplanationResult, InsufficientKnowledgeReason
from guidami_ai_patente.exceptions import ExplanationUnavailableError, QuestionNotFoundError
from guidami_ai_patente.models import (
    CitedGlossaryTerm,
    CommaSelection,
    Explanation,
    ExplanationRequest,
    GlossaryCandidate,
    QuestionContext,
    QuestionVocabularyContext,
)
from guidami_ai_patente.providers import LabelingStackProvider, LiveLabelingStackProvider
from guidami_ai_patente.repositories import GlossaryReadRepository, QuizQuestionRepository
from guidami_ai_patente.utils import merge_glossary_candidates, normalize_term_casing
from labeling import EMBEDDING_MODEL_COLUMN

from .current_labeling_read_service import CurrentLabelingReadService

logger = logging.getLogger(__name__)


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

    FR-10's grounding is enforced by `ExplanationWriterAgent` itself, via a pydantic-ai
    `output_validator` that retries an out-of-range ordinal in-conversation (mirroring
    `CommaLabelerAgent`, spec 0014). `_call_writer` no longer retries anything: it maps
    a raised exception — including `UnexpectedModelBehavior` once the agent's own retry
    budget (`config.num_retries`) is exhausted — to a 503, never a fabricated citation.

    Since spec 0020, `_explain` runs two independent stages concurrently via
    `asyncio.TaskGroup`: the legal explanation above (`_legal_outcome`, unchanged) and
    the vocabulary explanation (`_vocabulary_outcome`, new). `TaskGroup` — not
    `asyncio.gather` — is deliberate: `gather` does not cancel a sibling task merely
    because another one raised, which left `_vocabulary_outcome` running as an orphaned
    task (wasting an LLM call) past the point the caller had already handled the
    deadline. `TaskGroup` cancels every other task in the group the moment one of them
    raises, so a legal-stage failure now actually interrupts an in-flight vocabulary
    call. Because `TaskGroup` wraps a child's exception in an `ExceptionGroup` even when
    there is exactly one (Python 3.11+ semantics), `_explain` unwraps it back to the
    single underlying exception so `execute`'s `except TimeoutError` and every caller's
    `except ExplanationUnavailableError` keep working unchanged.

    The vocabulary stage never raises out of `_vocabulary_outcome` itself — any failure,
    including its own inner timeout (see below) or a malformed glossary row failing
    `CitedGlossaryTerm` validation, degrades to `(None, ())` (FR-5), so a vocabulary-stage
    outage can never turn into an outage of the already-shipped legal explanation (AD-1).
    `_vocabulary_outcome` also bounds its own work with an inner `asyncio.timeout`, sized
    to `explanation_deadline_s` minus `_VOCABULARY_DEADLINE_MARGIN_S`: without this, a
    slow vocabulary call could be the thing that fires the *outer*, shared deadline —
    which would 503 the legal stage too, even though the legal stage itself was fast.
    Before handing its retrieved candidates to `QuestionExplainerAgent`,
    `_vocabulary_outcome` shuffles them (`random.shuffle`, no fixed seed — this is live,
    per-request serving, unlike the batch labeler's seeded `shuffle_seed`) so retrieval
    rank never leaks in as an implicit relevance signal, then reuses that same shuffled
    list to resolve `cited_term_numbers` back into `CitedGlossaryTerm`s — deduplicated by
    `term.strip().casefold()` (first-cited order kept), since `glossary_entries` is only
    unique on `(source, article_number, comma_number, term)`, so two distinct rows can
    legitimately share a `term` and would otherwise produce duplicate
    `translation_hints`, which the translation endpoint's wire-layer validator rejects.

    Since spec 0021, `_vocabulary_outcome` gathers a second, independent glossary
    source alongside the existing DB read — a live `GlossaryEnricherAgent` call — and
    merges the two via `merge_glossary_candidates` (DB wins on conflict).
    """

    _VOCABULARY_DEADLINE_MARGIN_S = 2.0
    """Headroom subtracted from `explanation_deadline_s` for the vocabulary stage's own
    inner timeout, so a slow vocabulary call degrades on its own budget instead of
    tripping the shared outer deadline and 503ing the legal stage along with it."""

    config: Autowired[AppConfig]
    questions: Autowired[QuizQuestionRepository]
    reader: Autowired[CurrentLabelingReadService]
    writer: Autowired[ExplanationWriterAgent]
    vocabulary_agent: Autowired[QuestionExplainerAgent]
    glossary: Autowired[GlossaryReadRepository]
    enricher: Autowired[GlossaryEnricherAgent]
    judge_identity: Autowired[LabelingStackProvider]
    labeling_stack: Autowired[LiveLabelingStackProvider]

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
        """Renders the legal and vocabulary explanations, concurrently and independently.

        FR-1, FR-3, AD-1. Uses `asyncio.TaskGroup` so a legal-stage failure actually
        cancels the still-running vocabulary task (see class docstring) — the group
        wraps that failure in an `ExceptionGroup` even though it is the sole exception,
        so it is unwrapped back to the single underlying exception before propagating,
        to keep `execute`'s `except TimeoutError` and callers' `except
        ExplanationUnavailableError` working exactly as before this change.
        """
        selection = await self.reader(request.number)
        try:
            async with asyncio.TaskGroup() as group:
                legal_task = group.create_task(self._legal_outcome(selection, context, request))
                vocabulary_task = group.create_task(self._vocabulary_outcome(request.number))
        except ExceptionGroup as errors:
            raise errors.exceptions[0] from None

        term_explanation, translation_hints = vocabulary_task.result()
        return legal_task.result().model_copy(
            update={"term_explanation": term_explanation, "translation_hints": translation_hints}
        )

    async def _legal_outcome(
        self, selection: CommaSelection, context: QuestionContext, request: ExplanationRequest
    ) -> Explanation:
        """The unchanged spec 0017 legal-explanation path (FR-7)."""
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

    async def _vocabulary_outcome(
        self, number: str
    ) -> tuple[str | None, tuple[CitedGlossaryTerm, ...]]:
        """The vocabulary stage: never raises, degrades to `(None, ())` on any failure (FR-5).

        Since spec 0021, two independent sources of glossary candidates are gathered
        concurrently — `GlossaryReadRepository.candidates_for` (DB, unchanged) and
        `_enrich` (live, on-demand) — via `asyncio.gather(..., return_exceptions=True)`,
        not `TaskGroup`: a DB failure still degrades the whole stage exactly as before
        (FR-7), while a non-timeout `_enrich` exception is isolated to its own
        contribution and treated as an empty on-demand list (FR-7). `merge_glossary_
        candidates` then combines the two (FR-6, DB wins on a normalized-term conflict)
        before the existing shuffle and `QuestionExplainerAgent` call, whose own
        contract is unchanged (FR-5).

        Exactly one timeout bounds all of this: the pre-existing inner `asyncio.timeout`
        below, sized the same as before this spec. Its expiry cancels both gathered
        branches together and degrades the whole stage — there is no per-branch
        sub-budget (FR-7, resolved during the 2026-09-25 second grilling round: no
        timeout anywhere else in this codebase carries one, and a shared
        `asyncio.timeout` cancels every branch it wraps simultaneously on expiry, so it
        cannot be attributed to "only the enricher").

        `AppConfig.glossary.enabled=False` short-circuits before any of the above: no DB
        read, no `GlossaryEnricherAgent` call, no `QuestionExplainerAgent` call — not
        merely an empty result. This is a deployment kill switch, not a degrade path.
        """
        if not self.config.glossary.enabled:
            return None, ()

        vocabulary_deadline_s = max(
            self.config.explanation_deadline_s - self._VOCABULARY_DEADLINE_MARGIN_S, 0.0
        )
        variant = self.judge_identity.epoch.candidate_variant
        try:
            async with asyncio.timeout(vocabulary_deadline_s):
                context = await asyncio.to_thread(
                    self.questions.find_question_vocabulary_context, number, variant
                )
                assert context is not None  # `execute` already 404'd on an unknown number
                if context.embedding is None:
                    logger.warning(
                        "Quiz %s has no %s embedding; glossary retrieval is full-text only",
                        number,
                        variant,
                    )
                db_result, on_demand_result = await asyncio.gather(
                    asyncio.to_thread(
                        self.glossary.candidates_for, context.text, context.embedding
                    ),
                    self._enrich(number, context),
                    return_exceptions=True,
                )
                if isinstance(db_result, BaseException):
                    raise db_result
                if isinstance(on_demand_result, BaseException):
                    logger.warning(
                        "On-demand glossary enrichment failed for quiz %s",
                        number,
                        exc_info=on_demand_result,
                    )
                    on_demand_result = []
                candidates = merge_glossary_candidates(db_result, on_demand_result)
                random.shuffle(candidates)
                response = await self.vocabulary_agent.run(
                    QuestionExplainerRequest(
                        text=context.text,
                        image_description=context.image_description,
                        candidates=candidates,
                    )
                )
                hints = self._deduplicated_hints(candidates, response.cited_term_numbers)
        except Exception:
            logger.warning("Vocabulary stage failed for quiz %s", number, exc_info=True)
            return None, ()

        return response.explanation, hints

    async def _enrich(
        self, number: str, context: QuestionVocabularyContext
    ) -> list[tuple[str, str]]:
        """Runs the on-demand glossary agent, grounded on live comma retrieval (FR-1, FR-2).

        Reuses `LiveLabelingStackProvider` exactly as `CommaSelectorService._label_live`
        does for live comma labeling (AD-2): the same `find_with_vector` →
        `candidate_set` sequence, same epoch variant. `find_with_vector` returning
        `None` (not indexed under this variant) is not a failure — the agent still
        runs, with an empty comma list, falling back to general knowledge for every
        term (FR-2, FR-3). Any exception raised here (including
        `GlossaryEnricherResponse`'s own validator exhausting the agent's retries) is
        left to propagate to the caller's `asyncio.gather(..., return_exceptions=True)`,
        which is what isolates it to this branch alone (FR-7).

        `candidate_set` is a `CandidateSetService` (a `UseCase`), invoked via `__call__`
        (`.claude/rules/use-case-invocation.md`), crossed with `asyncio.to_thread`
        (AD-25) — the identical pattern `QuestionLabelingService.execute` already uses
        for this same collaborator (`src/labeling/services/question_labeling_service.py
        :79`), so this stage does not block the event loop on every `GET
        .../explanation` call (grilling, 2026-09-26: an earlier draft of this task
        called `.candidate_set.execute(row)` directly and synchronously, contradicting
        both AD-25 and the use-case-invocation rule).
        """
        epoch = self.judge_identity.epoch
        row = await asyncio.to_thread(
            self.labeling_stack.quiz.find_with_vector,
            number,
            epoch.candidate_variant,
            EMBEDDING_MODEL_COLUMN,
        )
        commas = (
            []
            if row is None
            else [
                candidate.comma
                for candidate in await asyncio.to_thread(self.labeling_stack.candidate_set, row)
            ]
        )
        response = await self.enricher.run(
            GlossaryEnricherRequest(
                text=context.text, image_description=context.image_description, commas=commas
            )
        )
        return [(entry.term, entry.definition) for entry in response.entries]

    @staticmethod
    def _deduplicated_hints(
        candidates: list[GlossaryCandidate], cited_term_numbers: list[int]
    ) -> tuple[CitedGlossaryTerm, ...]:
        """Resolves cited ordinals into hints, deduplicated by `term.strip().casefold()`.

        `glossary_entries` is unique on `(source, article_number, comma_number, term)`,
        so two distinct rows can legitimately share the same `term` (e.g. a CdS and a
        CAP definition of the same word); an on-demand candidate (spec 0021) can also
        collide with a DB one by case or stray whitespace. Keeping only the first-cited
        occurrence per normalized term avoids a duplicate-`term` payload, which
        `ExplanationTranslationRequest`'s wire-layer validator rejects with a 422.

        The `.strip()` is load-bearing (AD-6, spec 0021 second grilling round): bare
        `casefold()` alone does not normalize whitespace, so a term differing only by a
        leading/trailing space would otherwise survive as a separate hint.

        `candidate.definition_plain or candidate.definition` prefers the plain-language
        rendering (spec 0022 FR-5) and falls back to the verbatim legal text when a row
        has not been simplified yet (`definition_plain is None`) — always the case for
        an `AGENT_GENERATED` candidate (spec 0021 FR-6).

        `term=normalize_term_casing(candidate.term)` renders the displayed term in
        sentence case: DB-sourced terms are stored ALL CAPS by the build pipeline, while
        `GlossaryEnricherAgent`'s live terms preserve the question's own casing, and
        mixing both verbatim in the same response looked inconsistent. The dedup key
        above stays keyed on the raw `candidate.term` (casefold already ignores casing),
        so this display-only transform cannot affect which candidate is kept.
        """
        seen_terms: set[str] = set()
        hints: list[CitedGlossaryTerm] = []
        for ordinal in cited_term_numbers:
            candidate = candidates[ordinal - 1]
            term_key = candidate.term.strip().casefold()
            if term_key not in seen_terms:
                seen_terms.add(term_key)
                hints.append(
                    CitedGlossaryTerm(
                        term=normalize_term_casing(candidate.term),
                        definition=candidate.definition_plain or candidate.definition,
                        term_ru=candidate.term_ru,
                        origin=candidate.origin,
                    )
                )
        return tuple(hints)

    async def _call_writer(
        self, writer_request: ExplanationWriterRequest, number: str
    ) -> ExplanationWriterResponse:
        """Calls the writer, mapping any failure to a 503 (FR-10, FR-13).

        Raises:
            ExplanationUnavailableError: The writer raised, including
                `UnexpectedModelBehavior` once its own ordinal-grounding retries
                (FR-10, enforced by `ExplanationWriterAgent`'s `output_validator`) are
                exhausted.
        """
        try:
            return await self.writer.run(writer_request)
        except Exception as error:
            logger.warning("Explanation writer failed for quiz %s", number, exc_info=True)
            raise ExplanationUnavailableError(
                f"the explanation writer failed for question {number}"
            ) from error

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
