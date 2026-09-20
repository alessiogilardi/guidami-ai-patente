"""FR-6's remaining half: react to a reader miss by labeling live and writing through."""

from dataclasses import dataclass, field

import pytest

from domain.models.retrieval import QuizEvaluationRow
from guidami_ai_patente.exceptions import ExplanationUnavailableError, LabelingNotReadyError
from guidami_ai_patente.models import CommaSelection, CurrentLabeling, LabeledComma
from guidami_ai_patente.services import CommaSelectorService
from labeling.models import LabelingEpoch, QuestionLabelingRequest

_EPOCH = LabelingEpoch(
    judge_model="openrouter/google/gemini-2.5-flash-lite",
    prompt_version="0123456789abcdef",
    candidate_variant="topic_text",
    dense_k=50,
    text_k=50,
    lexeme_fields=("image_description", "text", "topic"),
)


def _labeling(*, has_commas: bool) -> CurrentLabeling:
    return CurrentLabeling(
        id=7,
        rationale="motivazione del giudice",
        has_supporting_commas=has_commas,
        origin="live",
        judge_model=_EPOCH.judge_model,
        human_validated=False,
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


def _row() -> QuizEvaluationRow:
    return QuizEvaluationRow(
        id=1,
        number="0001",
        topic="sosta",
        text="Domanda?",
        correct_answer=True,
        exact_keywords=None,
        image_filename=None,
        image_description=None,
        embedding=[0.1] * 4,
    )


@dataclass
class _ReaderDouble:
    """Stands in for `CurrentLabelingReadService`: a queue of results, popped per call.

    A queued `Exception` instance is raised instead of returned — used to simulate
    `LabelingNotReadyError` on a miss, and a later successful re-read after the live
    stage writes through.
    """

    results: list[CommaSelection | Exception] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    async def __call__(self, number: str) -> CommaSelection:
        self.calls.append(number)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@dataclass
class _QuizDouble:
    row: QuizEvaluationRow | None = None
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def find_with_vector(
        self, number: str, variant: str, model_column: str
    ) -> QuizEvaluationRow | None:
        self.calls.append((number, variant, model_column))
        return self.row


@dataclass
class _WriteDouble:
    runs: int = 0

    def find_or_create_live_run(self, run: object) -> int:
        self.runs += 1
        return 55


@dataclass
class _CorpusDouble:
    def comma_count(self) -> int:
        return 3


@dataclass
class _LabelingUnitDouble:
    labeling_id: int | None = 1
    error: Exception | None = None
    requests: list[QuestionLabelingRequest] = field(default_factory=list)

    async def __call__(self, request: QuestionLabelingRequest) -> int | None:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.labeling_id


@dataclass
class _LiveStackDouble:
    quiz: _QuizDouble
    golden_set: _WriteDouble
    question_labeling: _LabelingUnitDouble
    corpus: _CorpusDouble = field(default_factory=_CorpusDouble)


@dataclass
class _IdentityDouble:
    epoch: LabelingEpoch = _EPOCH


@dataclass
class _LabelingConfigDouble:
    shuffle_seed: int = 42


def _service(reader: _ReaderDouble, live_stack: _LiveStackDouble) -> CommaSelectorService:
    """Builds the service with doubles, bypassing the container."""
    service = object.__new__(CommaSelectorService)
    service.labeling_config = _LabelingConfigDouble()  # type: ignore[assignment]
    service.judge_identity = _IdentityDouble()  # type: ignore[assignment]
    service.live_stack = live_stack  # type: ignore[assignment]
    service.reader = reader  # type: ignore[assignment]
    return service


def _live_stack(**overrides: object) -> _LiveStackDouble:
    defaults: dict[str, object] = {
        "quiz": _QuizDouble(row=_row()),
        "golden_set": _WriteDouble(),
        "question_labeling": _LabelingUnitDouble(),
    }
    defaults.update(overrides)
    return _LiveStackDouble(**defaults)  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
async def test_a_reader_hit_is_returned_directly_with_no_live_work() -> None:
    """The plan's gate assertion 1, counted rather than inspected (FR-5)."""
    hit = CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),))
    reader = _ReaderDouble(results=[hit])
    live_stack = _live_stack()

    selection = await _service(reader, live_stack)("0001")

    assert selection is hit
    assert live_stack.quiz.calls == []
    assert live_stack.question_labeling.requests == []
    assert live_stack.golden_set.runs == 0


@pytest.mark.asyncio
async def test_a_not_indexed_reader_result_is_returned_directly() -> None:
    """FR-7's not_indexed: no vector, so no retrieval is attempted (FR-6)."""
    reader = _ReaderDouble(results=[CommaSelection(labeling=None)])
    live_stack = _live_stack()

    selection = await _service(reader, live_stack)("0001")

    assert selection.labeling is None
    assert live_stack.question_labeling.requests == []


@pytest.mark.asyncio
async def test_a_not_ready_reader_labels_live_and_serves_the_written_labeling() -> None:
    """Spec 0017 AD-3: the reader's miss signal is what triggers the live stage."""
    reader = _ReaderDouble(
        results=[
            LabelingNotReadyError("0001"),
            CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1), _comma(2))),
        ]
    )
    live_stack = _live_stack()

    selection = await _service(reader, live_stack)("0001")

    assert len(live_stack.question_labeling.requests) == 1
    assert [comma.judge_rank for comma in selection.commas] == [1, 2]
    assert reader.calls == ["0001", "0001"]


@pytest.mark.asyncio
async def test_the_vector_is_looked_up_under_the_epochs_variant() -> None:
    reader = _ReaderDouble(results=[LabelingNotReadyError("0042")])
    live_stack = _live_stack(quiz=_QuizDouble(row=None))

    await _service(reader, live_stack)("0042")

    assert live_stack.quiz.calls == [("0042", "topic_text", "embedding_3_small")]


@pytest.mark.asyncio
async def test_the_run_id_is_resolved_lazily_through_the_live_run_creator() -> None:
    """FR-9: the run is created on demand, once, by the shared write repository."""
    reader = _ReaderDouble(
        results=[
            LabelingNotReadyError("0001"),
            CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),)),
        ]
    )
    live_stack = _live_stack()

    await _service(reader, live_stack)("0001")

    assert live_stack.golden_set.runs == 0, "not resolved before the unit asks for it"
    assert live_stack.question_labeling.requests[0].resolve_run_id() == 55
    assert live_stack.golden_set.runs == 1


@pytest.mark.asyncio
async def test_a_discarded_write_serves_the_winners_labeling() -> None:
    """AD-19: losing the race is the designed outcome, never an error."""
    reader = _ReaderDouble(
        results=[
            LabelingNotReadyError("0001"),
            CommaSelection(labeling=_labeling(has_commas=True), commas=(_comma(1),)),
        ]
    )
    live_stack = _live_stack(question_labeling=_LabelingUnitDouble(labeling_id=None))

    selection = await _service(reader, live_stack)("0001")

    assert selection.labeling is not None
    assert [comma.judge_rank for comma in selection.commas] == [1]


@pytest.mark.asyncio
async def test_a_judge_failure_becomes_a_503() -> None:
    """AD-20: an outage must never be reported as a corpus gap."""
    reader = _ReaderDouble(results=[LabelingNotReadyError("0001")])
    live_stack = _live_stack(
        question_labeling=_LabelingUnitDouble(error=RuntimeError("provider is down"))
    )

    with pytest.raises(ExplanationUnavailableError):
        await _service(reader, live_stack)("0001")

    assert live_stack.golden_set.runs == 0, "AD-20: a raised judge must leave no run row"


@pytest.mark.asyncio
async def test_a_missing_labeling_after_a_successful_write_is_a_503() -> None:
    """A written labeling the reader still cannot see is an anomaly, not not_indexed."""
    reader = _ReaderDouble(results=[LabelingNotReadyError("0001"), LabelingNotReadyError("0001")])
    live_stack = _live_stack()

    with pytest.raises(ExplanationUnavailableError):
        await _service(reader, live_stack)("0001")
