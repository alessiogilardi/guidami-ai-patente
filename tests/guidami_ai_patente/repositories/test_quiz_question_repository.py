"""Integration tests for the API's quiz reads (spec 0012, FR-1/2/3/12/16)."""

from collections.abc import Iterator

import pytest
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.repositories import QuizQuestionRepository

_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
    "quiz_answers",
    "quiz_questions",
    "quiz_images",
)

_QUESTIONS = (
    ("0001", 1, "segnaletica", "Il segnale raffigurato vieta il sorpasso?", True, "s0001.jpeg"),
    ("0002", 2, "segnaletica", "Il segnale raffigurato indica un pericolo?", False, None),
    ("0003", 3, "velocità", "Il limite in autostrada è 130 km/h?", True, None),
    ("0004", 4, "velocità", "Il limite in centro abitato è 70 km/h?", False, None),
    ("0005", 5, "velocità", "La velocità va adeguata alle condizioni?", True, None),
)

_IMAGES = (("s0001.jpeg", "Segnale di divieto di sosta"),)


def _insert_questions(client: PostgresClient) -> None:
    client.execute_many(
        sql.SQL(
            "INSERT INTO quiz_questions "
            "(number, question_id, topic, text, correct_answer, image_filename) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        ),
        [list(row) for row in _QUESTIONS],
    )
    client.execute_many(
        sql.SQL("INSERT INTO quiz_images (filename, description) VALUES (%s, %s)"),
        [list(row) for row in _IMAGES],
    )


def _truncate_and_restart_identity(client: PostgresClient) -> None:
    """Truncates `_TABLES` and resets their `BIGSERIAL` sequences.

    `PostgresQuestionRepository.find_by_permutation`'s ranking hashes
    `id::text || seed`, so leaving a prior test's rows' `id` offset in place
    changes which `quiz_questions.id` values back this fixture's fixed 5-row bank
    — making `test_two_seeds_do_not_produce_the_same_whole_sequence` pass or fail
    depending on which other integration tests ran first in the same session.
    `PostgresClient.truncate` has no `RESTART IDENTITY` option, so this issues the
    raw statement directly via `client.execute`, scoped to this fixture only —
    not a change to `PostgresClient` itself.
    """
    query = sql.SQL("TRUNCATE TABLE {tables} RESTART IDENTITY").format(
        tables=sql.SQL(", ").join(sql.Identifier(name) for name in _TABLES)
    )
    client.execute(query)


@pytest.fixture
def bank(api_client: object) -> Iterator[PostgresClient]:
    """A five-question, one-image bank on the ephemeral stack, torn down after each test."""
    client = get_default_container().resolve(PostgresClientProvider).client
    _truncate_and_restart_identity(client)
    _insert_questions(client)
    yield client
    _truncate_and_restart_identity(client)


@pytest.fixture
def repository(api_client: object) -> QuizQuestionRepository:
    return get_default_container().resolve(QuizQuestionRepository)


@pytest.mark.integration
def test_the_same_seed_and_index_always_give_the_same_question(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    first = repository.find_by_permutation("abc", 0, None)
    second = repository.find_by_permutation("abc", 0, None)

    assert first is not None
    assert first.number == (second.number if second is not None else None)


@pytest.mark.integration
def test_consecutive_indices_give_different_questions(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    first = repository.find_by_permutation("abc", 0, None)
    second = repository.find_by_permutation("abc", 1, None)

    assert first is not None and second is not None
    assert first.number != second.number


@pytest.mark.integration
def test_walking_the_whole_bank_covers_every_question_exactly_once(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    walked = [repository.find_by_permutation("abc", index, None) for index in range(5)]

    numbers = [summary.number for summary in walked if summary is not None]
    assert sorted(numbers) == [number for number, *_ in _QUESTIONS]


@pytest.mark.integration
def test_two_seeds_do_not_produce_the_same_whole_sequence(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    def sequence(seed: str) -> list[str]:
        walked = [repository.find_by_permutation(seed, index, None) for index in range(5)]
        return [summary.number for summary in walked if summary is not None]

    assert sequence("abc") != sequence("zzz"), (
        "asserted over the whole sequence, not one index: two permutations may "
        "legitimately agree at a single position (FR-1)"
    )


@pytest.mark.integration
def test_the_topic_filter_holds_across_every_index(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    walked = [repository.find_by_permutation("abc", index, "velocità") for index in range(3)]

    assert all(summary is not None and summary.topic == "velocità" for summary in walked)


@pytest.mark.integration
def test_an_index_past_the_filtered_count_finds_nothing(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    assert repository.find_by_permutation("abc", 3, "velocità") is None


@pytest.mark.integration
def test_a_question_is_fetched_by_its_number(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    summary = repository.find_by_number("0001")

    assert summary is not None
    assert (summary.topic, summary.image_filename) == ("segnaletica", "s0001.jpeg")


@pytest.mark.integration
def test_an_unknown_number_fetches_nothing(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    assert repository.find_by_number("9999") is None


@pytest.mark.integration
def test_the_stored_answer_is_read_by_number(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    assert repository.find_correct_answer("0001") is True
    assert repository.find_correct_answer("0002") is False
    assert repository.find_correct_answer("9999") is None


@pytest.mark.integration
def test_topics_are_listed_with_counts_in_ascending_order(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    topics = repository.list_topics()

    assert [(topic.topic, topic.question_count) for topic in topics] == [
        ("segnaletica", 2),
        ("velocità", 3),
    ]


@pytest.mark.integration
def test_an_empty_bank_lists_no_topics(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    # All referencing tables in one statement: quiz_question_embeddings and
    # quiz_labelings both FK to quiz_questions, and Postgres refuses a single-table
    # TRUNCATE of a table still referenced by another.
    bank.truncate(*_TABLES)

    assert repository.list_topics() == []


@pytest.mark.integration
def test_only_a_referenced_filename_is_authorised(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    assert repository.image_is_referenced("s0001.jpeg") is True
    assert repository.image_is_referenced("never-referenced.png") is False


@pytest.mark.integration
def test_the_embedding_probe_sees_only_the_requested_variant(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    question_id = bank.fetch(sql.SQL("SELECT id FROM quiz_questions WHERE number = %s"), ["0001"])[
        0
    ][0]
    bank.execute(
        sql.SQL(
            "INSERT INTO quiz_question_embeddings (quiz_question_id, variant, embedding_3_small) "
            "VALUES (%s, %s, %s::vector)"
        ),
        [question_id, "topic_text", [0.0] * 1536],
    )

    assert repository.has_embedding("0001", "topic_text") is True
    assert repository.has_embedding("0001", "combined") is False
    assert repository.has_embedding("0002", "topic_text") is False


@pytest.mark.integration
def test_the_question_context_carries_the_answer_and_the_image_description(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    """FR-10: exactly what the writer must receive, in one read."""
    context = repository.find_question_context("0001")

    assert context is not None
    assert (context.correct_answer, context.image_description) == (
        True,
        "Segnale di divieto di sosta",
    )


@pytest.mark.integration
def test_an_image_less_question_has_no_description(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    context = repository.find_question_context("0002")

    assert context is not None
    assert context.image_description is None


@pytest.mark.integration
def test_an_unknown_number_has_no_context(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    assert repository.find_question_context("9999") is None


@pytest.mark.integration
def test_the_vocabulary_context_has_no_answer_field(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    """AD-4: no correct_answer anywhere in the returned shape."""
    context = repository.find_question_vocabulary_context("0001", "topic_text")

    assert context is not None
    assert "correct_answer" not in type(context).model_fields


def _store_embedding(bank: PostgresClient, number: str, variant: str) -> None:
    question_id = bank.fetch(sql.SQL("SELECT id FROM quiz_questions WHERE number = %s"), [number])[
        0
    ][0]
    bank.execute(
        sql.SQL(
            "INSERT INTO quiz_question_embeddings (quiz_question_id, variant, embedding_3_small) "
            "VALUES (%s, %s, %s::vector)"
        ),
        [question_id, variant, [0.0] * 1536],
    )


@pytest.mark.integration
def test_the_vocabulary_context_reads_the_requested_variant_embedding(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    _store_embedding(bank, "0001", "topic_text")

    context = repository.find_question_vocabulary_context("0001", "topic_text")

    assert context is not None
    assert context.embedding is not None


@pytest.mark.integration
def test_the_vocabulary_context_ignores_other_variants(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    """A stale `text` row must never stand in for the requested variant's vector."""
    _store_embedding(bank, "0001", "text")

    context = repository.find_question_vocabulary_context("0001", "topic_text")

    assert context is not None
    assert context.embedding is None


@pytest.mark.integration
def test_the_vocabulary_context_has_no_embedding_when_none_is_stored(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    """FR-4's full-text-only fallback starts here: `embedding` is `None`, not an error."""
    context = repository.find_question_vocabulary_context("0001", "topic_text")

    assert context is not None
    assert context.embedding is None


@pytest.mark.integration
def test_an_unknown_number_has_no_vocabulary_context(
    bank: PostgresClient, repository: QuizQuestionRepository
) -> None:
    assert repository.find_question_vocabulary_context("9999", "topic_text") is None
