"""Tests for GoldenSetLabelingService."""

from collections.abc import Sequence
from dataclasses import dataclass

import httpx
import pytest
from pydantic import BaseModel, ValidationError
from pydantic_ai.exceptions import ModelHTTPError

from domain.entities.evaluation import QuizCommaLabelEntity, QuizLabelingEntity
from domain.models.retrieval import QuizEvaluationRow, RetrievedComma
from retrieval_evaluation.exceptions import CandidateNumberOutOfRangeError
from retrieval_evaluation.models import CandidateComma
from retrieval_evaluation.services import GoldenSetLabelingService


@dataclass
class _FakeResponse:
    comma_numbers: list[int]
    rationale: str = "Motivazione."


def _make_row(row_id: int) -> QuizEvaluationRow:
    return QuizEvaluationRow(
        id=row_id,
        number=str(row_id),
        topic="Segnaletica",
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
    comma_id: int, dense_rank: int | None = None, text_rank: int | None = None
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


class _StubQuizRepository:
    def __init__(self, rows: Sequence[QuizEvaluationRow]) -> None:
        self._rows = list(rows)

    def fetch_with_vectors(self, variant: str, model_column: str) -> list[QuizEvaluationRow]:
        return list(self._rows)


class _FixedCandidateSetService:
    def __init__(self, candidates: Sequence[CandidateComma]) -> None:
        self._candidates = list(candidates)

    def build(self, row: QuizEvaluationRow) -> list[CandidateComma]:
        return list(self._candidates)


class _RecordingWriteRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[QuizLabelingEntity, list[QuizCommaLabelEntity]]] = []

    def insert_labeling(
        self, labeling: QuizLabelingEntity, labels: Sequence[QuizCommaLabelEntity]
    ) -> int:
        self.calls.append((labeling, list(labels)))
        return len(self.calls)


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
class _Counter:
    current: int = 0
    max_seen: int = 0

    def inc(self) -> None:
        self.current += 1
        self.max_seen = max(self.max_seen, self.current)

    def dec(self) -> None:
        self.current -= 1


class _TrackingCandidateSetService:
    def __init__(self, candidates: Sequence[CandidateComma], counter: _Counter) -> None:
        self._candidates = list(candidates)
        self._counter = counter

    def build(self, row: QuizEvaluationRow) -> list[CandidateComma]:
        self._counter.inc()
        return list(self._candidates)


class _TrackingWriteRepository:
    def __init__(self, counter: _Counter) -> None:
        self._counter = counter
        self.calls: list[tuple[QuizLabelingEntity, list[QuizCommaLabelEntity]]] = []

    def insert_labeling(
        self, labeling: QuizLabelingEntity, labels: Sequence[QuizCommaLabelEntity]
    ) -> int:
        self.calls.append((labeling, list(labels)))
        self._counter.dec()
        return len(self.calls)


class _ConcurrencyTrackingAgent:
    def __init__(self) -> None:
        self._counter = _Counter()

    @property
    def max_seen(self) -> int:
        return self._counter.max_seen

    async def run(self, request: object) -> _FakeResponse:
        import asyncio

        self._counter.inc()
        await asyncio.sleep(0)
        self._counter.dec()
        return _FakeResponse(comma_numbers=[])


def _make_service(
    quiz_repository: object,
    candidate_set_service: object,
    write_repository: object,
    agent: object,
    shuffle_seed: int = 42,
    max_concurrency: int = 8,
    transport_retries: int = 3,
    retry_backoff_seconds: float = 0.0,
    question_limit: int | None = None,
) -> GoldenSetLabelingService:
    return GoldenSetLabelingService(
        candidate_variant="topic_text",
        shuffle_seed=shuffle_seed,
        max_concurrency=max_concurrency,
        transport_retries=transport_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        question_limit=question_limit,
        quiz_repository=quiz_repository,  # type: ignore[arg-type]
        candidate_set_service=candidate_set_service,  # type: ignore[arg-type]
        write_repository=write_repository,  # type: ignore[arg-type]
        agent=agent,  # type: ignore[arg-type]
    )


async def test_the_presentation_order_is_identical_for_the_same_seed() -> None:
    candidates = [_make_candidate(i, dense_rank=i) for i in range(1, 21)]
    agent_a = _RecordingAgent()
    agent_b = _RecordingAgent()

    service_a = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService(candidates),
        _RecordingWriteRepository(),
        agent_a,
        shuffle_seed=7,
    )
    service_b = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService(candidates),
        _RecordingWriteRepository(),
        agent_b,
        shuffle_seed=7,
    )

    await service_a.label_all(run_id=1)
    await service_b.label_all(run_id=1)

    assert agent_a.received_candidate_ids[0] == agent_b.received_candidate_ids[0]


async def test_the_presentation_order_differs_for_different_seeds() -> None:
    candidates = [_make_candidate(i, dense_rank=i) for i in range(1, 21)]
    agent_a = _RecordingAgent()
    agent_b = _RecordingAgent()

    service_a = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService(candidates),
        _RecordingWriteRepository(),
        agent_a,
        shuffle_seed=1,
    )
    service_b = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService(candidates),
        _RecordingWriteRepository(),
        agent_b,
        shuffle_seed=2,
    )

    await service_a.label_all(run_id=1)
    await service_b.label_all(run_id=1)

    assert agent_a.received_candidate_ids[0] != agent_b.received_candidate_ids[0]


async def test_an_empty_number_list_writes_a_labeling_with_no_labels() -> None:
    write_repository = _RecordingWriteRepository()
    agent = _RecordingAgent(response_numbers=[], rationale="Nessun candidato pertinente.")
    service = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository,
        agent,
    )

    await service.label_all(run_id=1)

    assert agent.call_count == 1
    assert len(write_repository.calls) == 1
    labeling, labels = write_repository.calls[0]
    assert labels == []
    assert labeling.rationale == "Nessun candidato pertinente."


async def test_an_out_of_range_number_raises_and_writes_nothing() -> None:
    write_repository = _RecordingWriteRepository()
    candidates = [_make_candidate(10, dense_rank=1), _make_candidate(20, dense_rank=2)]
    agent = _RecordingAgent(response_numbers=[9])
    service = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService(candidates),
        write_repository,
        agent,
    )

    with pytest.raises(CandidateNumberOutOfRangeError):
        await service.label_all(run_id=1)

    assert write_repository.calls == []


async def test_numbers_resolve_to_the_presented_candidates_ids() -> None:
    write_repository = _RecordingWriteRepository()
    candidates = [
        _make_candidate(11, dense_rank=1),
        _make_candidate(22, dense_rank=2),
        _make_candidate(33, dense_rank=3),
    ]
    agent = _RecordingAgent(response_numbers=[2])
    service = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService(candidates),
        write_repository,
        agent,
    )

    await service.label_all(run_id=1)

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
    service = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService([both_arms, dense_only, text_only]),
        write_repository,
        agent,
    )

    await service.label_all(run_id=1)

    _, labels = write_repository.calls[0]
    assert [label.judge_rank for label in labels] == [1, 2, 3]
    assert {(label.article_comma_id, label.dense_rank, label.text_rank) for label in labels} == {
        (101, 3, 1),
        (102, 1, None),
        (103, None, 2),
    }


async def test_every_question_with_a_vector_is_labeled() -> None:
    write_repository = _RecordingWriteRepository()
    rows = [_make_row(i) for i in range(1, 6)]
    service = _make_service(
        _StubQuizRepository(rows),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository,
        _RecordingAgent(response_numbers=[]),
    )

    labeled = await service.label_all(run_id=1)

    assert labeled == 5
    assert len(write_repository.calls) == 5
    assert {call[0].quiz_question_id for call in write_repository.calls} == {1, 2, 3, 4, 5}


async def test_only_the_configured_number_of_questions_is_labeled_when_limited() -> None:
    write_repository = _RecordingWriteRepository()
    rows = [_make_row(i) for i in range(1, 11)]
    service = _make_service(
        _StubQuizRepository(rows),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository,
        _RecordingAgent(response_numbers=[]),
        question_limit=3,
    )

    labeled = await service.label_all(run_id=1)

    assert labeled == 3
    assert len(write_repository.calls) == 3


async def test_the_limited_subset_is_the_same_for_the_same_seed() -> None:
    rows = [_make_row(i) for i in range(1, 11)]
    write_repository_a = _RecordingWriteRepository()
    write_repository_b = _RecordingWriteRepository()
    service_a = _make_service(
        _StubQuizRepository(rows),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository_a,
        _RecordingAgent(response_numbers=[]),
        shuffle_seed=99,
        question_limit=3,
    )
    service_b = _make_service(
        _StubQuizRepository(rows),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository_b,
        _RecordingAgent(response_numbers=[]),
        shuffle_seed=99,
        question_limit=3,
    )

    await service_a.label_all(run_id=1)
    await service_b.label_all(run_id=1)

    ids_a = {call[0].quiz_question_id for call in write_repository_a.calls}
    ids_b = {call[0].quiz_question_id for call in write_repository_b.calls}
    assert ids_a == ids_b


async def test_no_limit_labels_every_question() -> None:
    rows = [_make_row(i) for i in range(1, 11)]
    write_repository = _RecordingWriteRepository()
    service = _make_service(
        _StubQuizRepository(rows),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository,
        _RecordingAgent(response_numbers=[]),
        question_limit=None,
    )

    await service.label_all(run_id=1)

    assert {call[0].quiz_question_id for call in write_repository.calls} == set(range(1, 11))


async def test_a_transport_error_is_retried_then_succeeds() -> None:
    write_repository = _RecordingWriteRepository()
    agent = _SequencedAgent(
        [httpx.ConnectError("boom"), httpx.ConnectError("boom"), _FakeResponse(comma_numbers=[])]
    )
    service = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository,
        agent,
        transport_retries=3,
        retry_backoff_seconds=0.0,
    )

    await service.label_all(run_id=1)

    assert agent.call_count == 3
    assert len(write_repository.calls) == 1


async def test_a_rate_limit_is_retried_but_an_auth_error_is_not() -> None:
    write_repository_retried = _RecordingWriteRepository()
    retried_agent = _SequencedAgent(
        [ModelHTTPError(status_code=429, model_name="m"), _FakeResponse(comma_numbers=[])]
    )
    retried_service = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository_retried,
        retried_agent,
        transport_retries=3,
        retry_backoff_seconds=0.0,
    )
    await retried_service.label_all(run_id=1)
    assert retried_agent.call_count == 2
    assert len(write_repository_retried.calls) == 1

    write_repository_permanent = _RecordingWriteRepository()
    permanent_agent = _SequencedAgent([ModelHTTPError(status_code=401, model_name="m")])
    permanent_service = _make_service(
        _StubQuizRepository([_make_row(2)]),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository_permanent,
        permanent_agent,
        transport_retries=3,
        retry_backoff_seconds=0.0,
    )

    with pytest.raises(ModelHTTPError):
        await permanent_service.label_all(run_id=1)

    assert permanent_agent.call_count == 1


async def test_a_validation_error_is_not_retried_as_transport() -> None:
    agent = _SequencedAgent([_make_validation_error()])
    service = _make_service(
        _StubQuizRepository([_make_row(1)]),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        _RecordingWriteRepository(),
        agent,
        transport_retries=3,
        retry_backoff_seconds=0.0,
    )

    with pytest.raises(ValidationError):
        await service.label_all(run_id=1)

    assert agent.call_count == 1


async def test_concurrency_never_exceeds_the_configured_bound() -> None:
    counter = _Counter()
    rows = [_make_row(i) for i in range(1, 21)]
    candidate_set_service = _TrackingCandidateSetService(
        [_make_candidate(1, dense_rank=1)], counter
    )
    write_repository = _TrackingWriteRepository(counter)
    agent = _ConcurrencyTrackingAgent()
    service = _make_service(
        _StubQuizRepository(rows),
        candidate_set_service,
        write_repository,
        agent,
        max_concurrency=3,
    )

    await service.label_all(run_id=1)

    assert agent.max_seen <= 3
    assert counter.max_seen <= 3
