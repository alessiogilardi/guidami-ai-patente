"""Tests for GoldenSetLabelingService.

The per-question judging sequence (retrieve, shuffle, judge, resolve ordinals, write,
including its transport retry policy) is exercised on `QuestionLabelingService` in
`test_question_labeling_service.py` (AD-12). What's left here is selection (topics,
limit) and the fan-out's own concurrency bound.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from domain.entities.evaluation import QuizCommaLabelEntity, QuizLabelingEntity
from domain.models.retrieval import QuizEvaluationRow, RetrievedComma
from labeling.models import CandidateComma
from labeling.services import GoldenSetLabelingService, QuestionLabelingService


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
    comma_id: int, dense_rank: int | None = None, text_rank: int | None = None
) -> CandidateComma:
    return CandidateComma(comma=_make_comma(comma_id), dense_rank=dense_rank, text_rank=text_rank)


class _StubQuizRepository:
    def __init__(self, rows: Sequence[QuizEvaluationRow]) -> None:
        self._rows = list(rows)

    def fetch_with_vectors(self, variant: str, model_column: str) -> list[QuizEvaluationRow]:
        return list(self._rows)


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

    def __call__(self, row: QuizEvaluationRow) -> list[CandidateComma]:
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
    question_limit: int | None = None,
    topics: Sequence[str] | None = None,
) -> GoldenSetLabelingService:
    question_labeling_service = QuestionLabelingService(
        shuffle_seed=shuffle_seed,
        transport_retries=3,
        retry_backoff_seconds=0.0,
        candidate_set_service=candidate_set_service,  # type: ignore[arg-type]
        write_repository=write_repository,  # type: ignore[arg-type]
        agent=agent,  # type: ignore[arg-type]
    )
    return GoldenSetLabelingService(
        candidate_variant="topic_text",
        shuffle_seed=shuffle_seed,
        max_concurrency=max_concurrency,
        question_limit=question_limit,
        topics=topics,
        quiz_repository=quiz_repository,  # type: ignore[arg-type]
        question_labeling_service=question_labeling_service,
    )


async def test_every_question_with_a_vector_is_labeled() -> None:
    write_repository = _RecordingWriteRepository()
    rows = [_make_row(i) for i in range(1, 6)]
    service = _make_service(
        _StubQuizRepository(rows),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository,
        _RecordingAgent(response_numbers=[]),
    )

    labeled = await service(1)

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

    labeled = await service(1)

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

    await service_a(1)
    await service_b(1)

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

    await service(1)

    assert {call[0].quiz_question_id for call in write_repository.calls} == set(range(1, 11))


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

    await service(1)

    assert agent.max_seen <= 3
    assert counter.max_seen <= 3


async def test_only_questions_of_the_named_topic_are_labeled() -> None:
    write_repository = _RecordingWriteRepository()
    rows = [_make_row(1, topic="velocità"), _make_row(2, topic="segnaletica")]
    service = _make_service(
        _StubQuizRepository(rows),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository,
        _RecordingAgent(response_numbers=[]),
        topics=["velocità"],
    )

    await service(1)

    assert [call[0].quiz_question_id for call in write_repository.calls] == [1]


async def test_repeated_topics_label_their_union() -> None:
    write_repository = _RecordingWriteRepository()
    rows = [
        _make_row(1, topic="velocità"),
        _make_row(2, topic="segnaletica"),
        _make_row(3, topic="precedenza"),
    ]
    service = _make_service(
        _StubQuizRepository(rows),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository,
        _RecordingAgent(response_numbers=[]),
        topics=["velocità", "precedenza"],
    )

    await service(1)

    assert sorted(call[0].quiz_question_id for call in write_repository.calls) == [1, 3]


async def test_no_topic_labels_the_whole_bank() -> None:
    write_repository = _RecordingWriteRepository()
    rows = [_make_row(1, topic="velocità"), _make_row(2, topic="segnaletica")]
    service = _make_service(
        _StubQuizRepository(rows),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository,
        _RecordingAgent(response_numbers=[]),
        topics=None,
    )

    labeled = await service(1)

    assert labeled == 2


async def test_the_limit_applies_to_the_filtered_set() -> None:
    """A count-only assertion here is too weak (final whole-branch review, Important #-).

    With 4 of 5 rows on-topic and a limit of 2, a filter-*after*-limit bug (limiting the
    unfiltered 5 rows to 2, then filtering those down by topic) could still produce
    `labeled == 2` a majority of the time depending on shuffle — the count alone doesn't
    distinguish "limit applied to the filtered set" from "limit applied before filtering
    happened to leave 2 on-topic rows". Asserting the labeled ids are a subset of the
    on-topic ids (and explicitly exclude the off-topic row) closes that gap.
    """
    write_repository = _RecordingWriteRepository()
    on_topic_ids = {1, 2, 3, 4}
    rows = [_make_row(i, topic="velocità") for i in on_topic_ids] + [
        _make_row(9, topic="segnaletica")
    ]
    service = _make_service(
        _StubQuizRepository(rows),
        _FixedCandidateSetService([_make_candidate(1, dense_rank=1)]),
        write_repository,
        _RecordingAgent(response_numbers=[]),
        topics=["velocità"],
        question_limit=2,
    )

    labeled = await service(1)

    assert labeled == 2
    labeled_ids = {call[0].quiz_question_id for call in write_repository.calls}
    assert len(labeled_ids) == 2
    assert labeled_ids <= on_topic_ids
    assert 9 not in labeled_ids
