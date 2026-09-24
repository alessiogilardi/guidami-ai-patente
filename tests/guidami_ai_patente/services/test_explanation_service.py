"""FR-5, FR-7, FR-10, FR-11, FR-13: render the commas, or refuse with a reason."""

import asyncio
import time
from dataclasses import dataclass, field

import pytest

from guidami_ai_patente.agents.explanation_writer.dto import (
    ExplanationWriterRequest,
    ExplanationWriterResponse,
)
from guidami_ai_patente.agents.question_explainer.dto import (
    QuestionExplainerRequest,
    QuestionExplainerResponse,
)
from guidami_ai_patente.enums import ExplanationResult, InsufficientKnowledgeReason
from guidami_ai_patente.exceptions import (
    ExplanationUnavailableError,
    LabelingNotReadyError,
    QuestionNotFoundError,
)
from guidami_ai_patente.models import (
    CitedGlossaryTerm,
    CommaSelection,
    CurrentLabeling,
    ExplanationRequest,
    GlossaryCandidate,
    LabeledComma,
    QuestionContext,
    QuestionVocabularyContext,
)
from guidami_ai_patente.services import ExplanationService


def _labeling(*, has_commas: bool = False, validated: bool = False) -> CurrentLabeling:
    """A current labeling whose flag agrees with the commas the test pairs it with."""
    return CurrentLabeling(
        id=7,
        rationale="nessun comma giustifica la risposta",
        has_supporting_commas=has_commas,
        origin="batch",
        judge_model="openrouter/google/gemini-2.5-flash-lite",
        human_validated=validated,
    )


def _comma(judge_rank: int) -> LabeledComma:
    return LabeledComma(
        source="cds",
        article_number="157",
        article_title="Sosta",
        comma_number=str(judge_rank),
        text="Testo.",
        judge_rank=judge_rank,
    )


def _vocabulary_context() -> QuestionVocabularyContext:
    return QuestionVocabularyContext(
        text="La carreggiata è larga?", image_description=None, embedding=None
    )


@dataclass
class _QuestionsDouble:
    context: QuestionContext | None = QuestionContext(
        text="Il segnale vieta la sosta?", correct_answer=True, image_description="Segnale"
    )
    vocabulary_context: QuestionVocabularyContext | None = field(
        default_factory=_vocabulary_context
    )

    def find_question_context(self, number: str) -> QuestionContext | None:
        return self.context

    def find_question_vocabulary_context(self, number: str) -> QuestionVocabularyContext | None:
        return self.vocabulary_context


@dataclass
class _ReaderDouble:
    selection: CommaSelection = field(default_factory=lambda: CommaSelection(labeling=None))
    calls: list[str] = field(default_factory=list)

    async def __call__(self, request: str) -> CommaSelection:
        self.calls.append(request)
        return self.selection


@dataclass
class _WriterDouble:
    responses: list[ExplanationWriterResponse] = field(default_factory=list)
    error: Exception | None = None
    delay: float = 0.0
    requests: list[ExplanationWriterRequest] = field(default_factory=list)

    async def run(self, request: ExplanationWriterRequest) -> ExplanationWriterResponse:
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.responses.pop(0)


@dataclass
class _ConfigDouble:
    explanation_deadline_s: float = 5.0


@dataclass
class _VocabularyAgentDouble:
    response: QuestionExplainerResponse | None = None
    error: Exception | None = None
    delay: float = 0.0
    requests: list[QuestionExplainerRequest] = field(default_factory=list)
    cancelled: bool = False

    async def run(self, request: QuestionExplainerRequest) -> QuestionExplainerResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.delay:
            try:
                await asyncio.sleep(self.delay)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        assert self.response is not None
        return self.response


@dataclass
class _GlossaryDouble:
    candidates: list[GlossaryCandidate] = field(default_factory=list)

    def candidates_for(self, text: str, embedding: list[float] | None) -> list[GlossaryCandidate]:
        return self.candidates


def _service(
    reader: _ReaderDouble,
    writer: _WriterDouble,
    questions: _QuestionsDouble | None = None,
    vocabulary_agent: _VocabularyAgentDouble | None = None,
    glossary: _GlossaryDouble | None = None,
) -> ExplanationService:
    service = object.__new__(ExplanationService)
    service.config = _ConfigDouble()  # type: ignore[assignment]
    service.questions = questions or _QuestionsDouble()  # type: ignore[assignment]
    service.reader = reader  # type: ignore[assignment]
    service.writer = writer  # type: ignore[assignment]
    service.vocabulary_agent = vocabulary_agent or _VocabularyAgentDouble(  # type: ignore[assignment]
        response=QuestionExplainerResponse(explanation="Spiegazione.", cited_term_numbers=[])
    )
    service.glossary = glossary or _GlossaryDouble()  # type: ignore[assignment]
    return service


def _explained(ordinals: list[int]) -> ExplanationWriterResponse:
    return ExplanationWriterResponse(
        explanation="La sosta è vietata perché la norma lo prevede.",
        cited_comma_numbers=ordinals,
    )


@pytest.mark.asyncio
async def test_the_vocabulary_stage_runs_even_when_the_legal_stage_refuses() -> None:
    """AD-1: independent of `result`."""
    vocabulary_agent = _VocabularyAgentDouble(
        response=QuestionExplainerResponse(
            explanation="La domanda chiede...", cited_term_numbers=[]
        )
    )
    explanation = await _service(
        _ReaderDouble(CommaSelection(labeling=_labeling())),
        _WriterDouble(),
        vocabulary_agent=vocabulary_agent,
    )(ExplanationRequest(number="0001"))

    assert explanation.result is ExplanationResult.INSUFFICIENT_KNOWLEDGE
    assert explanation.term_explanation == "La domanda chiede..."


@pytest.mark.asyncio
async def test_a_vocabulary_agent_failure_degrades_without_affecting_the_legal_stage() -> None:
    """FR-5: term_explanation becomes null, the legal explanation is untouched."""
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    vocabulary_agent = _VocabularyAgentDouble(error=RuntimeError("boom"))

    explanation = await _service(
        _ReaderDouble(selection),
        _WriterDouble(responses=[_explained([1])]),
        vocabulary_agent=vocabulary_agent,
    )(ExplanationRequest(number="0001"))

    assert explanation.result is ExplanationResult.EXPLAINED
    assert explanation.term_explanation is None
    assert explanation.translation_hints == ()


@pytest.mark.asyncio
async def test_cited_terms_are_resolved_into_translation_hints() -> None:
    candidate = GlossaryCandidate(
        id=1,
        source="cds",
        article_number="3",
        comma_number="1",
        term="carreggiata",
        definition="Parte della strada...",
        term_ru="проезжая часть",
    )
    vocabulary_agent = _VocabularyAgentDouble(
        response=QuestionExplainerResponse(
            explanation="La «carreggiata» è...", cited_term_numbers=[1]
        )
    )
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))

    explanation = await _service(
        _ReaderDouble(selection),
        _WriterDouble(responses=[_explained([1])]),
        vocabulary_agent=vocabulary_agent,
        glossary=_GlossaryDouble(candidates=[candidate]),
    )(ExplanationRequest(number="0001"))

    assert explanation.translation_hints == (
        CitedGlossaryTerm(
            term="carreggiata", definition="Parte della strada...", term_ru="проезжая часть"
        ),
    )


@pytest.mark.asyncio
async def test_a_null_term_ru_candidate_still_resolves_into_a_translation_hint() -> None:
    """Spec 0019 AD-11 regression, paired with the repository-level test.

    Before the fix, `GlossaryCandidate(term_ru=None)` (which `_row_to_candidate` builds
    for a row `translate-glossary-terms` has not reached yet) raised a
    `pydantic.ValidationError` when `_deduplicated_hints` rebuilt it as a
    `CitedGlossaryTerm` — caught by the broad `except Exception` around the whole
    vocabulary stage and logged as "Vocabulary stage failed", silently dropping the
    citation. This asserts the stage completes normally and the hint carries
    `term_ru=None` through, instead of degrading.
    """
    candidate = GlossaryCandidate(
        id=1,
        source="cds",
        article_number="3",
        comma_number="1",
        term="carreggiata",
        definition="Parte della strada...",
        term_ru=None,
    )
    vocabulary_agent = _VocabularyAgentDouble(
        response=QuestionExplainerResponse(
            explanation="La «carreggiata» è...", cited_term_numbers=[1]
        )
    )
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))

    explanation = await _service(
        _ReaderDouble(selection),
        _WriterDouble(responses=[_explained([1])]),
        vocabulary_agent=vocabulary_agent,
        glossary=_GlossaryDouble(candidates=[candidate]),
    )(ExplanationRequest(number="0001"))

    assert explanation.term_explanation == "La «carreggiata» è..."
    assert explanation.translation_hints == (
        CitedGlossaryTerm(term="carreggiata", definition="Parte della strada...", term_ru=None),
    )


def _candidate(ordinal: int, *, term: str | None = None) -> GlossaryCandidate:
    return GlossaryCandidate(
        id=ordinal,
        source="cds",
        article_number="3",
        comma_number=str(ordinal),
        term=term or f"term-{ordinal}",
        definition=f"Definizione {ordinal}.",
        term_ru=f"term-ru-{ordinal}",
    )


@pytest.mark.asyncio
async def test_citation_ordinals_resolve_against_the_shuffled_list_the_agent_saw() -> None:
    """The ordinal the agent returns is a 1-based index into the *shuffled* list it was shown.

    Not into `GlossaryReadRepository`'s RRF order — the service must reuse the same
    shuffled list for both prompt-building and ordinal resolution (grilling round,
    2026-09-23). `_VocabularyAgentDouble.requests` captures the exact request the agent
    received, so this test can assert against that list's own order rather than the
    glossary double's (RRF) order.

    Uses 5 candidates (not 2): with only 2, a double-shuffle regression (shuffling once
    for the prompt and again, differently, for ordinal resolution) has only a ~50%
    chance of producing a different order and being caught — 5 candidates make a
    coincidental match between two independent shuffles exceedingly unlikely (1/120).
    """
    candidates = [_candidate(i) for i in range(1, 6)]
    vocabulary_agent = _VocabularyAgentDouble(
        response=QuestionExplainerResponse(explanation="Testo.", cited_term_numbers=[2])
    )
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))

    explanation = await _service(
        _ReaderDouble(selection),
        _WriterDouble(responses=[_explained([1])]),
        vocabulary_agent=vocabulary_agent,
        glossary=_GlossaryDouble(candidates=candidates),
    )(ExplanationRequest(number="0001"))

    seen_candidates = vocabulary_agent.requests[0].candidates
    expected_term = seen_candidates[1].term  # ordinal 2 == index 1 of the list the agent saw
    assert explanation.translation_hints[0].term == expected_term


@pytest.mark.asyncio
async def test_duplicate_cited_terms_are_deduplicated_in_translation_hints() -> None:
    """FR-8 fix: two distinct rows sharing a `term` must not double up in the hints.

    `glossary_entries` is unique on `(source, article_number, comma_number, term)`, so
    a CdS and a CAP row can legitimately carry the same `term` — citing both must still
    resolve to a single `translation_hints` entry, or the translation endpoint's
    wire-layer validator 422s on the duplicate `term`.
    """
    first = GlossaryCandidate(
        id=1,
        source="cds",
        article_number="3",
        comma_number="1",
        term="obbligo",
        definition="Definizione CdS.",
        term_ru="obligation-cds",
    )
    second = GlossaryCandidate(
        id=2,
        source="cap",
        article_number="7",
        comma_number="2",
        term="Obbligo",  # same term, different case
        definition="Definizione CAP.",
        term_ru="obligation-cap",
    )
    vocabulary_agent = _VocabularyAgentDouble(
        response=QuestionExplainerResponse(explanation="Testo.", cited_term_numbers=[1, 2])
    )
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))

    explanation = await _service(
        _ReaderDouble(selection),
        _WriterDouble(responses=[_explained([1])]),
        vocabulary_agent=vocabulary_agent,
        glossary=_GlossaryDouble(candidates=[first, second]),
    )(ExplanationRequest(number="0001"))

    # `candidates` is shuffled before the agent sees it, so ordinal 1 may resolve to
    # either row depending on shuffle order — only the casefolded identity is stable.
    assert len(explanation.translation_hints) == 1
    assert explanation.translation_hints[0].term.casefold() == "obbligo"


@pytest.mark.asyncio
async def test_an_oversized_glossary_term_degrades_the_vocabulary_stage() -> None:
    """Fix #1: a `CitedGlossaryTerm` validation failure must stay inside the FR-5 boundary.

    `glossary_entries.term` is an unbounded `TEXT` column — nothing at the DB layer
    stops a term over `CitedGlossaryTerm`'s 80-char `max_length` from being cited.
    Before the fix, constructing `CitedGlossaryTerm` happened *after* the vocabulary
    stage's `try/except`, so this `ValidationError` escaped and crashed the whole
    request via `asyncio.gather`/`TaskGroup`, taking the already-shipped legal
    explanation down with it.
    """
    oversized = GlossaryCandidate(
        id=1,
        source="cds",
        article_number="3",
        comma_number="1",
        term="x" * 81,
        definition="Definizione.",
        term_ru="term-ru",
    )
    vocabulary_agent = _VocabularyAgentDouble(
        response=QuestionExplainerResponse(explanation="Testo.", cited_term_numbers=[1])
    )
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))

    explanation = await _service(
        _ReaderDouble(selection),
        _WriterDouble(responses=[_explained([1])]),
        vocabulary_agent=vocabulary_agent,
        glossary=_GlossaryDouble(candidates=[oversized]),
    )(ExplanationRequest(number="0001"))

    assert explanation.result is ExplanationResult.EXPLAINED
    assert explanation.term_explanation is None
    assert explanation.translation_hints == ()


@pytest.mark.asyncio
async def test_a_slow_vocabulary_stage_degrades_without_tripping_the_outer_deadline() -> None:
    """Fix #2b: the vocabulary stage's own inner timeout catches a slow call first.

    With `explanation_deadline_s=3.0`, the inner vocabulary budget is
    `3.0 - _VOCABULARY_DEADLINE_MARGIN_S == 1.0`. The vocabulary agent sleeps for 5s
    (far longer than either budget), so if the inner timeout is working the whole
    request should complete around the ~1.0s inner budget — never anywhere near the
    3.0s outer deadline, and the already-succeeding legal stage must not 503.
    """
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    vocabulary_agent = _VocabularyAgentDouble(
        delay=5.0,
        response=QuestionExplainerResponse(explanation="Testo.", cited_term_numbers=[]),
    )
    service = _service(
        _ReaderDouble(selection),
        _WriterDouble(responses=[_explained([1])]),
        vocabulary_agent=vocabulary_agent,
    )
    service.config = _ConfigDouble(explanation_deadline_s=3.0)  # type: ignore[assignment]

    started = time.monotonic()
    explanation = await service(ExplanationRequest(number="0001"))
    elapsed = time.monotonic() - started

    assert explanation.result is ExplanationResult.EXPLAINED
    assert explanation.term_explanation is None
    assert explanation.translation_hints == ()
    assert elapsed < 2.0  # well under the 3.0s outer deadline


@pytest.mark.asyncio
async def test_a_legal_stage_failure_cancels_the_still_running_vocabulary_task() -> None:
    """Fix #2a: `_legal_outcome` raising must actually cancel `_vocabulary_outcome`.

    The writer has a short delay (50ms) before raising — just long enough for the
    vocabulary task to actually start and enter its own 5s sleep, so the cancellation
    this test observes is a genuine mid-flight interruption, not merely "the sibling
    task was never scheduled." If the sibling were left running instead (the pre-fix
    `asyncio.gather` behavior), the double's `asyncio.CancelledError` handler would
    never fire and the whole call would take ~5s; the assertions below fail loudly in
    that case rather than just running slow.
    """
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(error=RuntimeError("provider is down"), delay=0.05)
    vocabulary_agent = _VocabularyAgentDouble(
        delay=5.0,
        response=QuestionExplainerResponse(explanation="Testo.", cited_term_numbers=[]),
    )

    started = time.monotonic()
    with pytest.raises(ExplanationUnavailableError):
        await _service(_ReaderDouble(selection), writer, vocabulary_agent=vocabulary_agent)(
            ExplanationRequest(number="0001")
        )
    elapsed = time.monotonic() - started

    assert elapsed < 1.0
    assert vocabulary_agent.cancelled is True


@pytest.mark.asyncio
async def test_a_missing_text_variant_embedding_logs_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """FR-4: no `text`-variant embedding row means the dense retrieval arm is skipped."""
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    questions = _QuestionsDouble(
        vocabulary_context=QuestionVocabularyContext(
            text="La carreggiata è larga?", image_description=None, embedding=None
        )
    )

    with caplog.at_level("WARNING"):
        await _service(
            _ReaderDouble(selection), _WriterDouble(responses=[_explained([1])]), questions
        )(ExplanationRequest(number="0001"))

    assert any("no text-variant embedding" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_a_present_text_variant_embedding_does_not_log_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    questions = _QuestionsDouble(
        vocabulary_context=QuestionVocabularyContext(
            text="La carreggiata è larga?", image_description=None, embedding=[0.1] * 1536
        )
    )

    with caplog.at_level("WARNING"):
        await _service(
            _ReaderDouble(selection), _WriterDouble(responses=[_explained([1])]), questions
        )(ExplanationRequest(number="0001"))

    assert not any("no text-variant embedding" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_an_unknown_question_is_a_404() -> None:
    service = _service(_ReaderDouble(), _WriterDouble(), _QuestionsDouble(context=None))

    with pytest.raises(QuestionNotFoundError):
        await service(ExplanationRequest(number="9999"))


@pytest.mark.asyncio
async def test_labeled_commas_are_rendered_and_cited() -> None:
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1), _comma(2)))
    writer = _WriterDouble(responses=[_explained([1, 2])])

    explanation = await _service(_ReaderDouble(selection), writer)(
        ExplanationRequest(number="0001")
    )

    assert explanation.result is ExplanationResult.EXPLAINED
    assert explanation.explanation is not None
    assert [comma.judge_rank for comma in explanation.citations] == [1, 2]


@pytest.mark.asyncio
async def test_the_provenance_of_the_used_labeling_is_returned() -> None:
    """FR-5: origin, human_validated and judge_model of the labeling that was used."""
    selection = CommaSelection(
        labeling=_labeling(has_commas=True, validated=True), commas=(_comma(1),)
    )
    writer = _WriterDouble(responses=[_explained([1])])

    explanation = await _service(_ReaderDouble(selection), writer)(
        ExplanationRequest(number="0001")
    )

    assert explanation.provenance is not None
    assert (explanation.provenance.origin, explanation.provenance.human_validated) == (
        "batch",
        True,
    )


@pytest.mark.asyncio
async def test_the_writer_receives_only_the_labeled_commas() -> None:
    """FR-10: exactly those N commas and no other candidate."""
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(responses=[_explained([1])])

    await _service(_ReaderDouble(selection), writer)(ExplanationRequest(number="0001"))

    assert len(writer.requests[0].commas) == 1


@pytest.mark.asyncio
async def test_the_writer_receives_the_question_answer_and_image_description() -> None:
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(responses=[_explained([1])])

    await _service(_ReaderDouble(selection), writer)(ExplanationRequest(number="0001"))

    sent = writer.requests[0]
    assert (sent.quiz_text, sent.correct_answer, sent.image_description) == (
        "Il segnale vieta la sosta?",
        True,
        "Segnale",
    )


@pytest.mark.asyncio
async def test_the_submitted_answer_reaches_the_writer() -> None:
    """FR-11: the explanation adapts to what the user answered."""
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(responses=[_explained([1])])

    await _service(_ReaderDouble(selection), writer)(
        ExplanationRequest(number="0001", submitted=False)
    )

    assert writer.requests[0].submitted_answer is False


@pytest.mark.asyncio
async def test_an_omitted_submitted_answer_is_served_normally() -> None:
    """FR-11: `None` is neutral, not an error."""
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(responses=[_explained([1])])

    explanation = await _service(_ReaderDouble(selection), writer)(
        ExplanationRequest(number="0001")
    )

    assert explanation.result is ExplanationResult.EXPLAINED
    assert writer.requests[0].submitted_answer is None


@pytest.mark.asyncio
async def test_an_empty_verdict_refuses_without_calling_the_writer() -> None:
    """FR-7: the writer is never invoked without supporting commas."""
    writer = _WriterDouble()

    explanation = await _service(_ReaderDouble(CommaSelection(labeling=_labeling())), writer)(
        ExplanationRequest(number="0001")
    )

    assert explanation.result is ExplanationResult.INSUFFICIENT_KNOWLEDGE
    assert (explanation.explanation, explanation.citations) == (None, ())
    assert writer.requests == []


@pytest.mark.asyncio
async def test_a_non_validated_empty_verdict_reads_no_supporting_norm() -> None:
    explanation = await _service(
        _ReaderDouble(CommaSelection(labeling=_labeling())), _WriterDouble()
    )(ExplanationRequest(number="0001"))

    assert explanation.reason is InsufficientKnowledgeReason.NO_SUPPORTING_NORM
    assert explanation.judge_rationale == "nessun comma giustifica la risposta"


@pytest.mark.asyncio
async def test_a_validated_empty_verdict_reads_confirmed() -> None:
    explanation = await _service(
        _ReaderDouble(CommaSelection(labeling=_labeling(validated=True))), _WriterDouble()
    )(ExplanationRequest(number="0001"))

    assert explanation.reason is InsufficientKnowledgeReason.NO_SUPPORTING_NORM_CONFIRMED


@pytest.mark.asyncio
async def test_no_labeling_at_all_reads_not_indexed_with_no_rationale() -> None:
    """FR-7: a pipeline gap, distinct from a corpus gap, and there is no judge to quote."""
    explanation = await _service(_ReaderDouble(CommaSelection(labeling=None)), _WriterDouble())(
        ExplanationRequest(number="0001")
    )

    assert explanation.reason is InsufficientKnowledgeReason.NOT_INDEXED
    assert explanation.judge_rationale is None


@pytest.mark.asyncio
async def test_the_service_calls_the_writer_once_and_trusts_its_output() -> None:
    """The service trusts the writer's output as-is; it no longer retries citations.

    FR-10 grounding now lives in `ExplanationWriterAgent`'s own `output_validator`
    (mirroring `CommaLabelerAgent`, spec 0014): the service no longer retries or
    range-checks `cited_comma_numbers` itself, it just renders what the writer returns.
    """
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(responses=[_explained([9])])

    explanation = await _service(_ReaderDouble(selection), writer)(
        ExplanationRequest(number="0001")
    )

    assert explanation.result is ExplanationResult.EXPLAINED
    assert len(writer.requests) == 1


@pytest.mark.asyncio
async def test_a_writer_failure_becomes_a_503() -> None:
    """FR-13: distinct from insufficient_knowledge, and carries no FR-7 reason."""
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(error=RuntimeError("provider is down"))

    with pytest.raises(ExplanationUnavailableError):
        await _service(_ReaderDouble(selection), writer)(ExplanationRequest(number="0001"))


@pytest.mark.asyncio
async def test_exceeding_the_deadline_becomes_a_503() -> None:
    """FR-13: a timeout is an outage, never a statement about the law."""

    @dataclass
    class _SlowSelector:
        calls: list[str] = field(default_factory=list)

        async def __call__(self, request: str) -> CommaSelection:
            await asyncio.sleep(1)
            return CommaSelection(labeling=None)

    service = _service(_SlowSelector(), _WriterDouble())  # type: ignore[arg-type]
    service.config = _ConfigDouble(explanation_deadline_s=0.01)  # type: ignore[assignment]

    with pytest.raises(ExplanationUnavailableError):
        await service(ExplanationRequest(number="0001"))


@pytest.mark.asyncio
async def test_exceeding_the_deadline_with_a_slow_writer_becomes_a_503() -> None:
    """D10: the single deadline spans the writer stage too, not just the selector."""

    @dataclass
    class _SlowWriter:
        requests: list[ExplanationWriterRequest] = field(default_factory=list)

        async def run(self, request: ExplanationWriterRequest) -> ExplanationWriterResponse:
            self.requests.append(request)
            await asyncio.sleep(1)
            return _explained([1])

    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    service = _service(_ReaderDouble(selection), _SlowWriter())  # type: ignore[arg-type]
    service.config = _ConfigDouble(explanation_deadline_s=0.01)  # type: ignore[assignment]

    started = time.monotonic()
    with pytest.raises(ExplanationUnavailableError):
        await service(ExplanationRequest(number="0001"))

    assert time.monotonic() - started < 0.5


@pytest.mark.asyncio
async def test_a_labeling_not_ready_error_propagates_uncaught() -> None:
    """Spec 0017 AD-4: a contract violation must not be reported as insufficient_knowledge."""

    @dataclass
    class _RaisingReader:
        async def __call__(self, request: str) -> CommaSelection:
            raise LabelingNotReadyError(request)

    service = _service(_RaisingReader(), _WriterDouble())  # type: ignore[arg-type]

    with pytest.raises(LabelingNotReadyError):
        await service(ExplanationRequest(number="0001"))
