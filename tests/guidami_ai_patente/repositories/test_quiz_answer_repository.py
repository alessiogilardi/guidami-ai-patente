"""Integration tests for QuizAnswerRepository (spec 0016, FR-5, FR-9, AD-16)."""

from collections.abc import Iterator

import pytest
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.repositories import QuizAnswerRepository, UserRepository

_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "quiz_question_embeddings",
    "quiz_answers",
    "users",
    "quiz_questions",
)

_QUESTION = ("0001", 1, "segnaletica", "Il segnale vieta il sorpasso?", True, None)


@pytest.fixture
def bank(api_client: object) -> Iterator[PostgresClient]:
    client = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(*_TABLES)
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_questions "
            "(number, question_id, topic, text, correct_answer, image_filename) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        ),
        list(_QUESTION),
    )
    get_default_container().resolve(UserRepository).provision(42)
    yield client
    client.truncate(*_TABLES)


@pytest.fixture
def repository(api_client: object) -> QuizAnswerRepository:
    return get_default_container().resolve(QuizAnswerRepository)


@pytest.mark.integration
def test_recording_an_answer_inserts_one_row_resolved_by_natural_keys(
    bank: PostgresClient, repository: QuizAnswerRepository
) -> None:
    repository.record_answer(42, "0001", "seed-abc", True)

    rows = bank.fetch(
        sql.SQL(
            "SELECT u.telegram_user_id, q.number, qa.session_id, qa.user_answer "
            "FROM quiz_answers qa "
            "JOIN users u ON u.id = qa.user_id "
            "JOIN quiz_questions q ON q.id = qa.quiz_id"
        )
    )
    assert rows == [(42, "0001", "seed-abc", True)]


@pytest.mark.integration
def test_the_same_question_can_be_answered_twice_without_deduplication(
    bank: PostgresClient, repository: QuizAnswerRepository
) -> None:
    repository.record_answer(42, "0001", "seed-abc", True)
    repository.record_answer(42, "0001", "seed-abc", False)

    count = bank.fetch(sql.SQL("SELECT count(*) FROM quiz_answers"))[0][0]
    assert count == 2


@pytest.mark.integration
def test_session_summary_counts_answered_and_correct(
    bank: PostgresClient, repository: QuizAnswerRepository
) -> None:
    repository.record_answer(42, "0001", "seed-abc", True)  # correct (stored answer is True)
    repository.record_answer(42, "0001", "seed-abc", False)  # wrong

    summary = repository.session_summary(42, "seed-abc")

    assert (summary.answered, summary.correct) == (2, 1)


@pytest.mark.integration
def test_session_summary_is_zero_for_a_session_with_no_answers(
    bank: PostgresClient, repository: QuizAnswerRepository
) -> None:
    summary = repository.session_summary(42, "never-played")

    assert (summary.answered, summary.correct) == (0, 0)


@pytest.mark.integration
def test_session_summary_is_scoped_to_the_requesting_user(
    bank: PostgresClient, repository: QuizAnswerRepository
) -> None:
    get_default_container().resolve(UserRepository).provision(99)
    repository.record_answer(42, "0001", "shared-seed", True)
    repository.record_answer(99, "0001", "shared-seed", True)

    summary = repository.session_summary(42, "shared-seed")

    assert summary.answered == 1
