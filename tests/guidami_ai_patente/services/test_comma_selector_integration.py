"""AD-20 and AD-29 against the real database: what a failure leaves behind."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.exceptions import ExplanationUnavailableError
from guidami_ai_patente.providers import LabelingStackProvider, LiveLabelingStackProvider
from guidami_ai_patente.repositories import GoldenSetReadRepository
from guidami_ai_patente.services import CommaSelectorService
from labeling import EMBEDDING_MODEL_COLUMN
from labeling.agents.comma_labeler.dto import CommaLabelerRequest, CommaLabelerResponse
from labeling.configs import LabelingConfig
from labeling.wiring import build_question_labeling_service

_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
    "quiz_questions",
    "article_commas",
    "articles",
)


@dataclass
class _RaisingAgent:
    error: Exception

    async def run(self, request: CommaLabelerRequest) -> CommaLabelerResponse:
        raise self.error


@dataclass
class _AnsweringAgent:
    ordinals: list[int]
    calls: list[CommaLabelerRequest] = field(default_factory=list)

    async def run(self, request: CommaLabelerRequest) -> CommaLabelerResponse:
        self.calls.append(request)
        return CommaLabelerResponse(
            comma_numbers=self.ordinals, rationale="il comma giustifica la risposta"
        )


@pytest.fixture
def live_corpus(api_client: object) -> Iterator[PostgresClient]:
    """One article with one comma (vectored), one question with a query vector."""
    client: PostgresClient = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(*_TABLES)

    article_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO articles (source, number, title, url, scraped_at) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            [
                "cds",
                "157",
                "Arresto, fermata e sosta dei veicoli",
                "https://example.test/art-157",
                datetime.now(UTC),
            ],
        )[0][0]
    )
    client.execute(
        sql.SQL(
            "INSERT INTO article_commas (article_id, comma_number, position, text, embedding) "
            "VALUES (%s, %s, %s, %s, %s::vector)"
        ),
        [article_id, "3", 0, "È vietata la sosta negli spazi riservati.", [0.1] * 1536],
    )
    question_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO quiz_questions (number, question_id, topic, text, correct_answer) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            ["0001", 1, "sosta", "È vietata la sosta?", True],
        )[0][0]
    )
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_question_embeddings (quiz_question_id, variant, {column}) "
            "VALUES (%s, %s, %s::vector)"
        ).format(column=sql.Identifier(EMBEDDING_MODEL_COLUMN)),
        [question_id, "topic_text", [0.1] * 1536],
    )
    yield client
    client.truncate(*_TABLES)


def _selector(agent: object) -> CommaSelectorService:
    """A real selector whose only substitute is the judge itself."""
    container = get_default_container()
    live_stack = container.resolve(LiveLabelingStackProvider)
    labeling_config = container.resolve(LabelingConfig)

    @dataclass
    class _LiveStack:
        quiz: object
        golden_set: object
        corpus: object
        question_labeling: object

    service = object.__new__(CommaSelectorService)
    service.labeling_config = labeling_config  # type: ignore[assignment]
    service.judge_identity = container.resolve(LabelingStackProvider)  # type: ignore[assignment]
    service.golden_set = container.resolve(GoldenSetReadRepository)  # type: ignore[assignment]
    service.live_stack = _LiveStack(  # type: ignore[assignment]
        quiz=live_stack.quiz,
        golden_set=live_stack.golden_set,
        corpus=live_stack.corpus,
        question_labeling=build_question_labeling_service(
            labeling_config,
            labeling_config.shuffle_seed,
            live_stack.candidate_set,
            live_stack.golden_set,
            agent,  # type: ignore[arg-type]
        ),
    )
    return service


def _counts(client: PostgresClient) -> tuple[int, int, int]:
    query = sql.SQL(
        "SELECT (SELECT count(*) FROM labeling_runs), "
        "(SELECT count(*) FROM quiz_labelings), (SELECT count(*) FROM quiz_comma_labels)"
    )
    runs, labelings, labels = client.fetch(query)[0]
    return int(runs), int(labelings), int(labels)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_judge_failure_writes_nothing_at_all(live_corpus: PostgresClient) -> None:
    """The plan's gate assertion 2 (AD-20, FR-13), counted in the database."""
    selector = _selector(_RaisingAgent(RuntimeError("provider is down")))

    with pytest.raises(ExplanationUnavailableError):
        await selector("0001")

    assert _counts(live_corpus) == (0, 0, 0), (
        "a failed judge must leave no trace: not a labeling, not a comma label, and "
        "not even a labeling_runs row — the run id is resolved only after a verdict"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_successful_judge_writes_the_run_the_labeling_and_its_commas(
    live_corpus: PostgresClient,
) -> None:
    """FR-6/FR-9: the live run is created once and the verdict is persisted."""
    selection = await _selector(_AnsweringAgent([1]))("0001")

    assert selection.labeling is not None
    assert len(selection.commas) == 1
    assert _counts(live_corpus) == (1, 1, 1)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_second_request_is_a_cache_hit_and_calls_no_judge(
    live_corpus: PostgresClient,
) -> None:
    """FR-6: unchanged configuration, so the second request issues no judge call."""
    await _selector(_AnsweringAgent([1]))("0001")

    second_agent = _AnsweringAgent([1])
    selection = await _selector(second_agent)("0001")

    assert second_agent.calls == []
    assert len(selection.commas) == 1
    assert _counts(live_corpus) == (1, 1, 1)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_an_empty_verdict_is_persisted_with_no_comma_rows(
    live_corpus: PostgresClient,
) -> None:
    """FR-6/FR-15: has_supporting_commas is false and there are zero children."""
    selection = await _selector(_AnsweringAgent([]))("0001")

    assert selection.commas == ()
    assert selection.labeling is not None
    assert selection.labeling.has_supporting_commas is False
    assert _counts(live_corpus) == (1, 1, 0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_repeated_miss_reuses_the_one_live_run(live_corpus: PostgresClient) -> None:
    """FR-9: one labeling_runs row per configuration epoch, however many requests."""
    await _selector(_AnsweringAgent([1]))("0001")

    live_corpus.execute(sql.SQL("DELETE FROM quiz_labelings"))
    await _selector(_AnsweringAgent([1]))("0001")

    runs, labelings, _ = _counts(live_corpus)
    assert (runs, labelings) == (1, 1)
