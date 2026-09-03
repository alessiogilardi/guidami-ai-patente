"""FR-5, FR-7, FR-10, FR-11, FR-13: render the commas, or refuse with a reason."""

import asyncio
import time
from dataclasses import dataclass, field

import pytest

from guidami_ai_patente.agents.explanation_writer.dto import (
    ExplanationWriterRequest,
    ExplanationWriterResponse,
)
from guidami_ai_patente.enums import ExplanationResult, InsufficientKnowledgeReason
from guidami_ai_patente.exceptions import ExplanationUnavailableError, QuestionNotFoundError
from guidami_ai_patente.models import (
    CommaSelection,
    CurrentLabeling,
    ExplanationRequest,
    LabeledComma,
    QuestionContext,
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


@dataclass
class _QuestionsDouble:
    context: QuestionContext | None = QuestionContext(
        text="Il segnale vieta la sosta?", correct_answer=True, image_description="Segnale"
    )

    def find_question_context(self, number: str) -> QuestionContext | None:
        return self.context


@dataclass
class _SelectorDouble:
    selection: CommaSelection = field(default_factory=lambda: CommaSelection(labeling=None))
    calls: list[str] = field(default_factory=list)

    async def __call__(self, request: str) -> CommaSelection:
        self.calls.append(request)
        return self.selection


@dataclass
class _WriterDouble:
    responses: list[ExplanationWriterResponse] = field(default_factory=list)
    error: Exception | None = None
    requests: list[ExplanationWriterRequest] = field(default_factory=list)

    async def run(self, request: ExplanationWriterRequest) -> ExplanationWriterResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.responses.pop(0)


@dataclass
class _ConfigDouble:
    explanation_deadline_s: float = 5.0


def _service(
    selector: _SelectorDouble,
    writer: _WriterDouble,
    questions: _QuestionsDouble | None = None,
) -> ExplanationService:
    service = object.__new__(ExplanationService)
    service.config = _ConfigDouble()  # type: ignore[assignment]
    service.questions = questions or _QuestionsDouble()  # type: ignore[assignment]
    service.selector = selector  # type: ignore[assignment]
    service.writer = writer  # type: ignore[assignment]
    return service


def _explained(ordinals: list[int]) -> ExplanationWriterResponse:
    return ExplanationWriterResponse(
        explanation="La sosta è vietata perché la norma lo prevede.",
        cited_comma_numbers=ordinals,
    )


@pytest.mark.asyncio
async def test_an_unknown_question_is_a_404() -> None:
    service = _service(_SelectorDouble(), _WriterDouble(), _QuestionsDouble(context=None))

    with pytest.raises(QuestionNotFoundError):
        await service(ExplanationRequest(number="9999"))


@pytest.mark.asyncio
async def test_labeled_commas_are_rendered_and_cited() -> None:
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1), _comma(2)))
    writer = _WriterDouble(responses=[_explained([1, 2])])

    explanation = await _service(_SelectorDouble(selection), writer)(
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

    explanation = await _service(_SelectorDouble(selection), writer)(
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

    await _service(_SelectorDouble(selection), writer)(ExplanationRequest(number="0001"))

    assert len(writer.requests[0].commas) == 1


@pytest.mark.asyncio
async def test_the_writer_receives_the_question_answer_and_image_description() -> None:
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(responses=[_explained([1])])

    await _service(_SelectorDouble(selection), writer)(ExplanationRequest(number="0001"))

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

    await _service(_SelectorDouble(selection), writer)(
        ExplanationRequest(number="0001", submitted=False)
    )

    assert writer.requests[0].submitted_answer is False


@pytest.mark.asyncio
async def test_an_omitted_submitted_answer_is_served_normally() -> None:
    """FR-11: `None` is neutral, not an error."""
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(responses=[_explained([1])])

    explanation = await _service(_SelectorDouble(selection), writer)(
        ExplanationRequest(number="0001")
    )

    assert explanation.result is ExplanationResult.EXPLAINED
    assert writer.requests[0].submitted_answer is None


@pytest.mark.asyncio
async def test_an_empty_verdict_refuses_without_calling_the_writer() -> None:
    """FR-7: the writer is never invoked without supporting commas."""
    writer = _WriterDouble()

    explanation = await _service(_SelectorDouble(CommaSelection(labeling=_labeling())), writer)(
        ExplanationRequest(number="0001")
    )

    assert explanation.result is ExplanationResult.INSUFFICIENT_KNOWLEDGE
    assert (explanation.explanation, explanation.citations) == (None, ())
    assert writer.requests == []


@pytest.mark.asyncio
async def test_a_non_validated_empty_verdict_reads_no_supporting_norm() -> None:
    explanation = await _service(
        _SelectorDouble(CommaSelection(labeling=_labeling())), _WriterDouble()
    )(ExplanationRequest(number="0001"))

    assert explanation.reason is InsufficientKnowledgeReason.NO_SUPPORTING_NORM
    assert explanation.judge_rationale == "nessun comma giustifica la risposta"


@pytest.mark.asyncio
async def test_a_validated_empty_verdict_reads_confirmed() -> None:
    explanation = await _service(
        _SelectorDouble(CommaSelection(labeling=_labeling(validated=True))), _WriterDouble()
    )(ExplanationRequest(number="0001"))

    assert explanation.reason is InsufficientKnowledgeReason.NO_SUPPORTING_NORM_CONFIRMED


@pytest.mark.asyncio
async def test_no_labeling_at_all_reads_not_indexed_with_no_rationale() -> None:
    """FR-7: a pipeline gap, distinct from a corpus gap, and there is no judge to quote."""
    explanation = await _service(_SelectorDouble(CommaSelection(labeling=None)), _WriterDouble())(
        ExplanationRequest(number="0001")
    )

    assert explanation.reason is InsufficientKnowledgeReason.NOT_INDEXED
    assert explanation.judge_rationale is None


@pytest.mark.asyncio
async def test_an_out_of_range_citation_is_retried_then_becomes_a_503() -> None:
    """FR-10/AD-14: grounding is enforced, not requested."""
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(responses=[_explained([4]), _explained([9]), _explained([7])])

    with pytest.raises(ExplanationUnavailableError):
        await _service(_SelectorDouble(selection), writer)(ExplanationRequest(number="0001"))

    assert len(writer.requests) == 3


@pytest.mark.asyncio
async def test_a_retry_that_cites_correctly_is_accepted() -> None:
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(responses=[_explained([5]), _explained([1])])

    explanation = await _service(_SelectorDouble(selection), writer)(
        ExplanationRequest(number="0001")
    )

    assert explanation.result is ExplanationResult.EXPLAINED
    assert len(writer.requests) == 2


@pytest.mark.asyncio
async def test_a_writer_failure_becomes_a_503() -> None:
    """FR-13: distinct from insufficient_knowledge, and carries no FR-7 reason."""
    selection = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    writer = _WriterDouble(error=RuntimeError("provider is down"))

    with pytest.raises(ExplanationUnavailableError):
        await _service(_SelectorDouble(selection), writer)(ExplanationRequest(number="0001"))


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
    service = _service(_SelectorDouble(selection), _SlowWriter())  # type: ignore[arg-type]
    service.config = _ConfigDouble(explanation_deadline_s=0.01)  # type: ignore[assignment]

    started = time.monotonic()
    with pytest.raises(ExplanationUnavailableError):
        await service(ExplanationRequest(number="0001"))

    assert time.monotonic() - started < 0.5
