"""Tests for QuestionLabelingService.

The per-question judging sequence (retrieve, shuffle, judge, resolve ordinals, write)
lives here, extracted out of `GoldenSetLabelingService` so the batch pass and the
future live/API caller share exactly one implementation (see the class docstring for
why that matters — the epoch key does not capture presentation order, prompt text or
retry policy).
"""

from collections.abc import Sequence
from dataclasses import dataclass

import httpx
import pytest
from pydantic import BaseModel, ValidationError
from pydantic_ai.exceptions import ModelHTTPError

from domain.entities.evaluation import QuizCommaLabelEntity, QuizLabelingEntity
from domain.models.retrieval import QuizEvaluationRow, RetrievedComma
from labeling.agents.comma_labeler.dto import CommaLabelerRequest, CommaLabelerResponse
from labeling.exceptions import CandidateNumberOutOfRangeError
from labeling.models import CandidateComma, QuestionLabelingRequest
from labeling.services import QuestionLabelingService


@dataclass
class _FakeResponse:
    comma_numbers: list[int]
    rationale: str = "Motivazione."


def _make_row(row_id: int, topic: str = "Segnaletica") -> QuizEvaluationRow:
    return QuizEvaluationRow(
        id=row_id,
        number=str(row_id),
        topic=topic,
        text="Domanda di prova.",
        correct_answer=True,
        exact_keywords=None,
        image_filename=None,
        image_description=None,
        embedding=[0.1, 0.2],
    )


def _make_comma(comma_id: int) -> RetrievedComma:
    return RetrievedComma(
        id=comma_id,
        source="cds",
        article_number="41",
        article_title="Segnali di pericolo",
        comma_number="1",
        text=f"Testo {comma_id}.",
        distance=0.1,
    )


def _make_candidate(
    comma_id: int, dense_rank: int | None = 1, text_rank: int | None = None
) -> CandidateComma:
    return CandidateComma(comma=_make_comma(comma_id), dense_rank=dense_rank, text_rank=text_rank)


def _make_validation_error() -> ValidationError:
    class _Probe(BaseModel):
        value: int

    try:
        _Probe(value=object())  # type: ignore[arg-type]
    except ValidationError as exc:
        return exc
    raise AssertionError("expected _Probe(value=object()) to raise ValidationError")


class _FixedCandidateSetService:
    def __init__(self, candidates: Sequence[CandidateComma]) -> None:
        self._candidates = list(candidates)

    def __call__(self, row: QuizEvaluationRow) -> list[CandidateComma]:
        return list(self._candidates)


class _RecordingWriteRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[QuizLabelingEntity, list[QuizCommaLabelEntity]]] = []

    def insert_labeling(
        self, labeling: QuizLabelingEntity, labels: Sequence[QuizCommaLabelEntity]
    ) -> int:
        self.calls.append((labeling, list(labels)))
        return len(self.calls)

    @property
    def labelings(self) -> list[QuizLabelingEntity]:
        return [labeling for labeling, _ in self.calls]


class _RecordingAgent:
    """Captures, per call, the candidate ids presented in `request.candidates`."""

    def __init__(
        self, response_numbers: list[int] | None = None, rationale: str = "Motivazione."
    ) -> None:
        self._response_numbers = response_numbers if response_numbers is not None else []
        self._rationale = rationale
        self.received_candidate_ids: list[list[int]] = []
        self.call_count = 0

    async def run(self, request: object) -> _FakeResponse:
        self.call_count += 1
        self.received_candidate_ids.append(
            [comma.id for comma in request.candidates]  # type: ignore[attr-defined]
        )
        return _FakeResponse(comma_numbers=self._response_numbers, rationale=self._rationale)


class _SequencedAgent:
    """Raises/returns one scripted side effect per call, in order."""

    def __init__(self, side_effects: Sequence[object]) -> None:
        self._side_effects = list(side_effects)
        self.call_count = 0

    async def run(self, request: object) -> _FakeResponse:
        self.call_count += 1
        effect = self._side_effects[self.call_count - 1]
        if isinstance(effect, BaseException):
            raise effect
        return effect  # type: ignore[return-value]


@dataclass
class _RaisingAgent:
    error: Exception

    async def run(self, request: CommaLabelerRequest) -> CommaLabelerResponse:
        raise self.error


@dataclass
class _ConflictingWriteRepository:
    def insert_labeling(
        self, labeling: QuizLabelingEntity, labels: Sequence[QuizCommaLabelEntity]
    ) -> int | None:
        return None


def _service(
    candidates: list[CandidateComma],
    agent: object,
    write_repository: object,
    *,
    shuffle_seed: int = 42,
) -> QuestionLabelingService:
    return QuestionLabelingService(
        shuffle_seed=shuffle_seed,
        transport_retries=3,
        retry_backoff_seconds=0.0001,
        candidate_set_service=_FixedCandidateSetService(candidates),  # type: ignore[arg-type]
        write_repository=write_repository,  # type: ignore[arg-type]
        agent=agent,  # type: ignore[arg-type]
    )


async def test_the_presentation_order_is_identical_for_the_same_seed() -> None:
    candidates = [_make_candidate(i, dense_rank=i) for i in range(1, 21)]
    agent_a = _RecordingAgent()
    agent_b = _RecordingAgent()

    service_a = _service(candidates, agent_a, _RecordingWriteRepository(), shuffle_seed=7)
    service_b = _service(candidates, agent_b, _RecordingWriteRepository(), shuffle_seed=7)

    await service_a(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))
    await service_b(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))

    assert agent_a.received_candidate_ids[0] == agent_b.received_candidate_ids[0]


async def test_the_presentation_order_differs_for_different_seeds() -> None:
    candidates = [_make_candidate(i, dense_rank=i) for i in range(1, 21)]
    agent_a = _RecordingAgent()
    agent_b = _RecordingAgent()

    service_a = _service(candidates, agent_a, _RecordingWriteRepository(), shuffle_seed=1)
    service_b = _service(candidates, agent_b, _RecordingWriteRepository(), shuffle_seed=2)

    await service_a(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))
    await service_b(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))

    assert agent_a.received_candidate_ids[0] != agent_b.received_candidate_ids[0]


async def test_an_empty_number_list_writes_a_labeling_with_no_labels() -> None:
    write_repository = _RecordingWriteRepository()
    agent = _RecordingAgent(response_numbers=[], rationale="Nessun candidato pertinente.")
    service = _service([_make_candidate(1, dense_rank=1)], agent, write_repository)

    await service(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))

    assert agent.call_count == 1
    assert len(write_repository.calls) == 1
    labeling, labels = write_repository.calls[0]
    assert labels == []
    assert labeling.rationale == "Nessun candidato pertinente."


async def test_an_out_of_range_number_raises_and_writes_nothing() -> None:
    write_repository = _RecordingWriteRepository()
    candidates = [_make_candidate(10, dense_rank=1), _make_candidate(20, dense_rank=2)]
    agent = _RecordingAgent(response_numbers=[9])
    service = _service(candidates, agent, write_repository)

    with pytest.raises(CandidateNumberOutOfRangeError):
        await service(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))

    assert write_repository.calls == []


async def test_numbers_resolve_to_the_presented_candidates_ids() -> None:
    write_repository = _RecordingWriteRepository()
    candidates = [
        _make_candidate(11, dense_rank=1),
        _make_candidate(22, dense_rank=2),
        _make_candidate(33, dense_rank=3),
    ]
    agent = _RecordingAgent(response_numbers=[2])
    service = _service(candidates, agent, write_repository)

    await service(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))

    presented_ids = agent.received_candidate_ids[0]
    _, labels = write_repository.calls[0]
    assert len(labels) == 1
    assert labels[0].article_comma_id == presented_ids[1]


async def test_each_label_carries_the_rank_each_arm_gave_it() -> None:
    write_repository = _RecordingWriteRepository()
    both_arms = _make_candidate(101, dense_rank=3, text_rank=1)
    dense_only = _make_candidate(102, dense_rank=1, text_rank=None)
    text_only = _make_candidate(103, dense_rank=None, text_rank=2)
    agent = _RecordingAgent(response_numbers=[1, 2, 3])
    service = _service([both_arms, dense_only, text_only], agent, write_repository)

    await service(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))

    _, labels = write_repository.calls[0]
    assert [label.judge_rank for label in labels] == [1, 2, 3]
    assert {(label.article_comma_id, label.dense_rank, label.text_rank) for label in labels} == {
        (101, 3, 1),
        (102, 1, None),
        (103, None, 2),
    }


async def test_a_transport_error_is_retried_then_succeeds() -> None:
    write_repository = _RecordingWriteRepository()
    agent = _SequencedAgent(
        [httpx.ConnectError("boom"), httpx.ConnectError("boom"), _FakeResponse(comma_numbers=[])]
    )
    service = _service([_make_candidate(1, dense_rank=1)], agent, write_repository)

    await service(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))

    assert agent.call_count == 3
    assert len(write_repository.calls) == 1


async def test_a_rate_limit_is_retried_but_an_auth_error_is_not() -> None:
    write_repository_retried = _RecordingWriteRepository()
    retried_agent = _SequencedAgent(
        [ModelHTTPError(status_code=429, model_name="m"), _FakeResponse(comma_numbers=[])]
    )
    retried_service = _service(
        [_make_candidate(1, dense_rank=1)], retried_agent, write_repository_retried
    )
    await retried_service(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))
    assert retried_agent.call_count == 2
    assert len(write_repository_retried.calls) == 1

    write_repository_permanent = _RecordingWriteRepository()
    permanent_agent = _SequencedAgent([ModelHTTPError(status_code=401, model_name="m")])
    permanent_service = _service(
        [_make_candidate(1, dense_rank=1)], permanent_agent, write_repository_permanent
    )

    with pytest.raises(ModelHTTPError):
        await permanent_service(
            QuestionLabelingRequest(row=_make_row(2), resolve_run_id=lambda: 1)
        )

    assert permanent_agent.call_count == 1


async def test_a_validation_error_is_not_retried_as_transport() -> None:
    agent = _SequencedAgent([_make_validation_error()])
    service = _service([_make_candidate(1, dense_rank=1)], agent, _RecordingWriteRepository())

    with pytest.raises(ValidationError):
        await service(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))

    assert agent.call_count == 1


@pytest.mark.asyncio
async def test_the_run_id_is_resolved_only_once_a_verdict_exists() -> None:
    """FR-13/AD-20: a judge failure must leave no `labeling_runs` row behind."""
    calls: list[str] = []

    def resolve() -> int:
        calls.append("resolved")
        return 7

    agent = _RaisingAgent(RuntimeError("provider is down"))
    service = _service([_make_candidate(1)], agent, _RecordingWriteRepository())

    with pytest.raises(RuntimeError):
        await service(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=resolve))

    assert calls == [], (
        "the run id must be resolved after the judge answers, not before: resolving it "
        "eagerly would create a labeling_runs row for a run that produced nothing"
    )


@pytest.mark.asyncio
async def test_the_resolved_run_id_is_written_on_the_labeling() -> None:
    write_repository = _RecordingWriteRepository()
    service = _service([_make_candidate(1)], _RecordingAgent([1]), write_repository)

    await service(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 99))

    assert write_repository.labelings[0].run_id == 99


@pytest.mark.asyncio
async def test_a_discarded_write_returns_none() -> None:
    """AD-19: the losing racer gets `None`, and it is not an error here."""
    service = _service([_make_candidate(1)], _RecordingAgent([1]), _ConflictingWriteRepository())

    result = await service(QuestionLabelingRequest(row=_make_row(1), resolve_run_id=lambda: 1))

    assert result is None
