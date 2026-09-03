"""FR-6's two paths: serve the cache, or compute live and write through."""

from dataclasses import dataclass, field

import pytest

from domain.models.retrieval import QuizEvaluationRow
from guidami_ai_patente.exceptions import ExplanationUnavailableError
from guidami_ai_patente.models import CurrentLabeling, LabeledComma
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


def _labeling(*, has_commas: bool, validated: bool = False) -> CurrentLabeling:
    return CurrentLabeling(
        id=7,
        rationale="motivazione del giudice",
        has_supporting_commas=has_commas,
        origin="live",
        judge_model=_EPOCH.judge_model,
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
class _GoldenSetDouble:
    labelings: list[CurrentLabeling | None] = field(default_factory=list)
    commas: list[LabeledComma] = field(default_factory=list)
    comma_reads: list[int] = field(default_factory=list)

    def find_current_labeling(self, number: str, epoch: LabelingEpoch) -> CurrentLabeling | None:
        return self.labelings.pop(0) if self.labelings else None

    def find_labeled_commas(self, labeling_id: int) -> list[LabeledComma]:
        self.comma_reads.append(labeling_id)
        return list(self.commas)


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


def _service(
    golden_set: _GoldenSetDouble,
    live_stack: _LiveStackDouble,
) -> CommaSelectorService:
    """Builds the service with doubles, bypassing the container.

    `object.__new__` sidesteps pywire's instrumented `__init__`; the class has no
    constructor body, so assigning the four fields is the whole of its construction.
    """
    service = object.__new__(CommaSelectorService)
    service.labeling_config = _LabelingConfigDouble()  # type: ignore[assignment]
    service.judge_identity = _IdentityDouble()  # type: ignore[assignment]
    service.live_stack = live_stack  # type: ignore[assignment]
    service.golden_set = golden_set  # type: ignore[assignment]
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
async def test_a_cache_hit_returns_the_labeled_commas() -> None:
    golden_set = _GoldenSetDouble(labelings=[_labeling(has_commas=True)], commas=[_comma(1)])

    selection = await _service(golden_set, _live_stack())("0001")

    assert selection.labeling is not None
    assert [comma.judge_rank for comma in selection.commas] == [1]


@pytest.mark.asyncio
async def test_a_cache_hit_issues_no_retrieval_and_no_judge_call() -> None:
    """The plan's gate assertion 1, counted rather than inspected (FR-5)."""
    golden_set = _GoldenSetDouble(labelings=[_labeling(has_commas=True)], commas=[_comma(1)])
    live_stack = _live_stack()

    await _service(golden_set, live_stack)("0001")

    assert live_stack.quiz.calls == []
    assert live_stack.question_labeling.requests == []
    assert live_stack.golden_set.runs == 0


@pytest.mark.asyncio
async def test_an_empty_verdict_returns_the_labeling_with_no_commas() -> None:
    """FR-7: the judge already answered; re-asking under one epoch would cost the same."""
    golden_set = _GoldenSetDouble(labelings=[_labeling(has_commas=False)])
    live_stack = _live_stack()

    selection = await _service(golden_set, live_stack)("0001")

    assert selection.labeling is not None
    assert selection.commas == ()
    assert golden_set.comma_reads == [], "no child read when the flag says there are none"
    assert live_stack.question_labeling.requests == []


@pytest.mark.asyncio
async def test_no_vector_is_reported_as_no_labeling_at_all() -> None:
    """FR-7's not_indexed: no retrieval is attempted (FR-6)."""
    live_stack = _live_stack(quiz=_QuizDouble(row=None))

    selection = await _service(_GoldenSetDouble(), live_stack)("0001")

    assert selection.labeling is None
    assert selection.commas == ()
    assert live_stack.question_labeling.requests == []


@pytest.mark.asyncio
async def test_the_vector_is_looked_up_under_the_epochs_variant() -> None:
    live_stack = _live_stack(quiz=_QuizDouble(row=None))

    await _service(_GoldenSetDouble(), live_stack)("0042")

    assert live_stack.quiz.calls == [("0042", "topic_text", "embedding_3_small")]


@pytest.mark.asyncio
async def test_a_cache_miss_labels_live_and_serves_the_written_labeling() -> None:
    golden_set = _GoldenSetDouble(
        labelings=[None, _labeling(has_commas=True)], commas=[_comma(1), _comma(2)]
    )
    live_stack = _live_stack()

    selection = await _service(golden_set, live_stack)("0001")

    assert len(live_stack.question_labeling.requests) == 1
    assert [comma.judge_rank for comma in selection.commas] == [1, 2]


@pytest.mark.asyncio
async def test_the_run_id_is_resolved_lazily_through_the_live_run_creator() -> None:
    """FR-9: the run is created on demand, once, by the shared write repository."""
    golden_set = _GoldenSetDouble(labelings=[None, _labeling(has_commas=True)], commas=[_comma(1)])
    live_stack = _live_stack()

    await _service(golden_set, live_stack)("0001")

    assert live_stack.golden_set.runs == 0, "not resolved before the unit asks for it"
    assert live_stack.question_labeling.requests[0].resolve_run_id() == 55
    assert live_stack.golden_set.runs == 1


@pytest.mark.asyncio
async def test_a_discarded_write_serves_the_winners_labeling() -> None:
    """AD-19: losing the race is the designed outcome, never an error."""
    golden_set = _GoldenSetDouble(labelings=[None, _labeling(has_commas=True)], commas=[_comma(1)])
    live_stack = _live_stack(question_labeling=_LabelingUnitDouble(labeling_id=None))

    selection = await _service(golden_set, live_stack)("0001")

    assert selection.labeling is not None
    assert [comma.judge_rank for comma in selection.commas] == [1]


@pytest.mark.asyncio
async def test_a_judge_failure_becomes_a_503() -> None:
    """AD-20: an outage must never be reported as a corpus gap."""
    live_stack = _live_stack(
        question_labeling=_LabelingUnitDouble(error=RuntimeError("provider is down"))
    )

    with pytest.raises(ExplanationUnavailableError):
        await _service(_GoldenSetDouble(labelings=[None]), live_stack)("0001")


@pytest.mark.asyncio
async def test_a_missing_labeling_after_a_successful_write_is_a_503() -> None:
    """A written labeling the precedence query cannot see is an anomaly, not not_indexed."""
    live_stack = _live_stack()

    with pytest.raises(ExplanationUnavailableError):
        await _service(_GoldenSetDouble(labelings=[None, None]), live_stack)("0001")


@pytest.mark.asyncio
async def test_a_cascaded_away_child_set_reads_as_no_commas() -> None:
    """AD-10's detection hole: the flag says true, the rows are gone."""
    golden_set = _GoldenSetDouble(labelings=[_labeling(has_commas=True)], commas=[])

    selection = await _service(golden_set, _live_stack())("0001")

    assert selection.commas == ()
    assert golden_set.comma_reads == [7]
