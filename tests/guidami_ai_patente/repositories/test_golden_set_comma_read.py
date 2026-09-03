"""FR-5's citation read: the labeled commas, in the judge's own order."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.repositories import GoldenSetReadRepository

_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
    "quiz_questions",
    "article_commas",
    "articles",
)


@pytest.fixture
def seeded(api_client: object) -> Iterator[tuple[GoldenSetReadRepository, int]]:
    """Seeds one labeling with three commas whose judge order is not their id order."""
    container = get_default_container()
    client: PostgresClient = container.resolve(PostgresClientProvider).client
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
    comma_ids = [
        int(
            client.fetch(
                sql.SQL(
                    "INSERT INTO article_commas (article_id, comma_number, position, text) "
                    "VALUES (%s, %s, %s, %s) RETURNING id"
                ),
                [article_id, comma_number, position, f"Testo del comma {comma_number}."],
            )[0][0]
        )
        for position, comma_number in enumerate(("1", "2", "3"))
    ]
    question_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO quiz_questions (number, question_id, topic, text, correct_answer) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            ["0001", 1, "sosta", "Domanda?", True],
        )[0][0]
    )
    run_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO labeling_runs (judge_model, prompt_version, candidate_variant, "
                "dense_k, text_k, lexeme_fields, shuffle_seed, corpus_commit, "
                "corpus_comma_count) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"
            ),
            ["m", "v", "topic_text", 50, 50, ["text"], 42, "deadbeef", 3],
        )[0][0]
    )
    labeling_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO quiz_labelings (run_id, quiz_question_id, rationale, "
                "has_supporting_commas) VALUES (%s, %s, %s, TRUE) RETURNING id"
            ),
            [run_id, question_id, "trovato"],
        )[0][0]
    )
    # judge_rank deliberately inverse to insertion order, so an unordered read fails.
    for judge_rank, comma_id in zip((3, 1, 2), comma_ids, strict=True):
        client.execute(
            sql.SQL(
                "INSERT INTO quiz_comma_labels "
                "(labeling_id, article_comma_id, judge_rank, dense_rank) "
                "VALUES (%s, %s, %s, %s)"
            ),
            [labeling_id, comma_id, judge_rank, 1],
        )

    yield container.resolve(GoldenSetReadRepository), labeling_id
    client.truncate(*_TABLES)


@pytest.mark.integration
def test_the_commas_come_back_ordered_by_judge_rank(
    seeded: tuple[GoldenSetReadRepository, int],
) -> None:
    repository, labeling_id = seeded

    commas = repository.find_labeled_commas(labeling_id)

    assert [comma.judge_rank for comma in commas] == [1, 2, 3]
    assert [comma.comma_number for comma in commas] == ["2", "3", "1"]


@pytest.mark.integration
def test_each_comma_carries_its_article_identity(
    seeded: tuple[GoldenSetReadRepository, int],
) -> None:
    """FR-5: source, article number and title, comma number, text, rank."""
    repository, labeling_id = seeded

    first = repository.find_labeled_commas(labeling_id)[0]

    assert (first.source, first.article_number, first.article_title) == (
        "cds",
        "157",
        "Arresto, fermata e sosta dei veicoli",
    )
    assert first.text == "Testo del comma 2."


@pytest.mark.integration
def test_a_labeling_with_no_commas_reads_as_empty(
    seeded: tuple[GoldenSetReadRepository, int],
) -> None:
    """The empty verdict is a legitimate outcome, never an error (FR-7)."""
    repository, labeling_id = seeded

    assert repository.find_labeled_commas(labeling_id + 10_000) == []
