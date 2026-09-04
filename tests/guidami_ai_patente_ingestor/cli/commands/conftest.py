"""Fixtures for `cli/commands` tests that need a seeded golden-set Postgres.

Mirrors the seeding helpers in `tests/labeling/repositories/test_golden_set_schema.py`:
one article -> one comma -> one quiz question -> one labeling run -> one labeling, with
`validated_at`/`validated_by` set only on the "validated" variant. Table order matches
`GoldenSetWriteRepository`'s FK chain so the truncate-before/after step never fails.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig

_GOLDEN_SET_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
    "quiz_questions",
    "article_commas",
    "articles",
)


@pytest.fixture
def ingestor_test_config(postgres_test_config: PostgresConnectionConfig) -> IngestorConfig:
    """`IngestorConfig` pointed at the isolated integration-test Postgres."""
    return IngestorConfig.load(postgres=postgres_test_config)


def _insert_article(client: PostgresClient) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO articles (source, number, title, url, scraped_at) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        ["cds", "1", "Titolo", "https://example.test", datetime.now(UTC)],
    )
    return rows[0][0]


def _insert_comma(client: PostgresClient, article_id: int) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO article_commas (article_id, comma_number, position, text, embedding) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        [article_id, "1", 0, "Testo comma 1.", None],
    )
    return rows[0][0]


def _insert_quiz_question(client: PostgresClient) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO quiz_questions (number, question_id, topic, text, correct_answer) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        ["00001", 1, "segnaletica", "Domanda di prova?", True],
    )
    return rows[0][0]


def _insert_run(client: PostgresClient) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO labeling_runs (judge_model, prompt_version, candidate_variant, "
            "dense_k, text_k, lexeme_fields, shuffle_seed, corpus_commit, "
            "corpus_comma_count, origin) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"
        ),
        [
            "openrouter/google/gemini-2.5-flash-lite",
            "0" * 16,
            "topic_text",
            50,
            50,
            ["topic"],
            42,
            "0" * 40,
            1,
            "live",
        ],
    )
    return rows[0][0]


def _insert_labeling(
    client: PostgresClient,
    run_id: int,
    question_id: int,
    *,
    validated_at: datetime | None,
    validated_by: str | None,
) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO quiz_labelings "
            "(run_id, quiz_question_id, rationale, has_supporting_commas, "
            "validated_at, validated_by) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id"
        ),
        [run_id, question_id, "Motivazione.", False, validated_at, validated_by],
    )
    return rows[0][0]


def _seed_one_labeling(
    client: PostgresClient, *, validated_at: datetime | None, validated_by: str | None
) -> None:
    article_id = _insert_article(client)
    _insert_comma(client, article_id)
    question_id = _insert_quiz_question(client)
    run_id = _insert_run(client)
    _insert_labeling(
        client, run_id, question_id, validated_at=validated_at, validated_by=validated_by
    )


@pytest.fixture
def seeded_labeling(ingestor_test_config: IngestorConfig) -> Iterator[None]:
    """Seeds article -> comma -> question -> run -> an unvalidated labeling."""
    with PostgresClient(ingestor_test_config.postgres) as client:
        client.truncate(*_GOLDEN_SET_TABLES)
        _seed_one_labeling(client, validated_at=None, validated_by=None)
        yield
        client.truncate(*_GOLDEN_SET_TABLES)


@pytest.fixture
def seeded_validated_labeling(ingestor_test_config: IngestorConfig) -> Iterator[None]:
    """Seeds the same chain, with `validated_at`/`validated_by` set on the labeling."""
    with PostgresClient(ingestor_test_config.postgres) as client:
        client.truncate(*_GOLDEN_SET_TABLES)
        _seed_one_labeling(client, validated_at=datetime.now(UTC), validated_by="alessio.gilardi")
        yield
        client.truncate(*_GOLDEN_SET_TABLES)
