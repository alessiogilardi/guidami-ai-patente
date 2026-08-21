from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.evaluation import (
    LabelingRunEntity,
    QuizCommaLabelEntity,
    QuizLabelingEntity,
)
from retrieval_evaluation.repositories import GoldenSetWriteRepository

_GOLDEN_SET_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
    "quiz_questions",
    "article_commas",
    "articles",
)


@dataclass
class _Fixture:
    client: PostgresClient
    article_comma_ids: list[int]
    quiz_question_ids: list[int]


def _insert_article(client: PostgresClient) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO articles (source, number, title, url, scraped_at) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        ["cds", "1", "Titolo", "https://example.test", datetime.now(UTC)],
    )
    return rows[0][0]


def _insert_comma(client: PostgresClient, article_id: int, comma_number: str) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO article_commas (article_id, comma_number, position, text, embedding) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        [article_id, comma_number, 0, f"Testo comma {comma_number}.", None],
    )
    return rows[0][0]


def _insert_quiz_question(client: PostgresClient, number: str, question_id: int) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO quiz_questions (number, question_id, topic, text, correct_answer) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        [number, question_id, "segnaletica", "Domanda di prova?", True],
    )
    return rows[0][0]


@pytest.fixture
def fixture(postgres_test_config: PostgresConnectionConfig) -> Iterator[_Fixture]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate(*_GOLDEN_SET_TABLES)
        article_id = _insert_article(client)
        comma_ids = [_insert_comma(client, article_id, str(i)) for i in range(1, 4)]
        question_ids = [_insert_quiz_question(client, f"000{i}", i) for i in range(1, 3)]
        yield _Fixture(client=client, article_comma_ids=comma_ids, quiz_question_ids=question_ids)
        client.truncate(*_GOLDEN_SET_TABLES)


def _make_repository(client: PostgresClient) -> GoldenSetWriteRepository:
    return GoldenSetWriteRepository("labeling_runs", "quiz_labelings", "quiz_comma_labels", client)


def _insert_run(client: PostgresClient) -> int:
    return _make_repository(client).insert_run(
        LabelingRunEntity(
            judge_model="openrouter/google/gemini-2.5-flash-lite",
            prompt_version="0" * 16,
            candidate_variant="topic_text",
            dense_k=50,
            text_k=50,
            shuffle_seed=42,
            corpus_commit="0" * 40,
            corpus_comma_count=3,
            question_limit=None,
        )
    )


@pytest.mark.integration
def test_a_labeling_with_two_commas_writes_one_parent_and_two_children(
    fixture: _Fixture,
) -> None:
    run_id = _insert_run(fixture.client)
    repository = _make_repository(fixture.client)
    labels = [
        QuizCommaLabelEntity(
            article_comma_id=fixture.article_comma_ids[0], judge_rank=1, dense_rank=1
        ),
        QuizCommaLabelEntity(
            article_comma_id=fixture.article_comma_ids[1], judge_rank=2, dense_rank=2
        ),
    ]

    repository.insert_labeling(
        QuizLabelingEntity(
            run_id=run_id,
            quiz_question_id=fixture.quiz_question_ids[0],
            rationale="Motivazione.",
        ),
        labels,
    )

    labeling_rows = fixture.client.fetch(
        sql.SQL("SELECT id, rationale FROM quiz_labelings WHERE quiz_question_id = %s"),
        [fixture.quiz_question_ids[0]],
    )
    assert len(labeling_rows) == 1
    labeling_id, rationale = labeling_rows[0]
    assert rationale == "Motivazione."

    child_rows = fixture.client.fetch(
        sql.SQL("SELECT count(*) FROM quiz_comma_labels WHERE labeling_id = %s"),
        [labeling_id],
    )
    assert child_rows[0][0] == 2


@pytest.mark.integration
def test_a_labeling_with_no_comma_writes_the_parent_and_no_children(fixture: _Fixture) -> None:
    run_id = _insert_run(fixture.client)
    repository = _make_repository(fixture.client)

    repository.insert_labeling(
        QuizLabelingEntity(
            run_id=run_id,
            quiz_question_id=fixture.quiz_question_ids[0],
            rationale="Nessun comma pertinente.",
        ),
        [],
    )

    labeling_rows = fixture.client.fetch(
        sql.SQL("SELECT id FROM quiz_labelings WHERE quiz_question_id = %s"),
        [fixture.quiz_question_ids[0]],
    )
    assert len(labeling_rows) == 1
    labeling_id = labeling_rows[0][0]

    child_rows = fixture.client.fetch(
        sql.SQL("SELECT count(*) FROM quiz_comma_labels WHERE labeling_id = %s"),
        [labeling_id],
    )
    assert child_rows[0][0] == 0


@pytest.mark.integration
def test_an_unsubmitted_question_has_no_labeling_row(fixture: _Fixture) -> None:
    run_id = _insert_run(fixture.client)
    repository = _make_repository(fixture.client)

    repository.insert_labeling(
        QuizLabelingEntity(
            run_id=run_id,
            quiz_question_id=fixture.quiz_question_ids[0],
            rationale="Motivazione.",
        ),
        [],
    )

    unsubmitted_rows = fixture.client.fetch(
        sql.SQL("SELECT id FROM quiz_labelings WHERE quiz_question_id = %s"),
        [fixture.quiz_question_ids[1]],
    )
    assert unsubmitted_rows == []


@pytest.mark.integration
def test_the_outcome_is_derivable_by_counting_children(fixture: _Fixture) -> None:
    run_id = _insert_run(fixture.client)
    repository = _make_repository(fixture.client)

    repository.insert_labeling(
        QuizLabelingEntity(
            run_id=run_id,
            quiz_question_id=fixture.quiz_question_ids[0],
            rationale="Con commi.",
        ),
        [
            QuizCommaLabelEntity(
                article_comma_id=fixture.article_comma_ids[0], judge_rank=1, dense_rank=1
            ),
            QuizCommaLabelEntity(
                article_comma_id=fixture.article_comma_ids[1], judge_rank=2, dense_rank=2
            ),
        ],
    )
    repository.insert_labeling(
        QuizLabelingEntity(
            run_id=run_id,
            quiz_question_id=fixture.quiz_question_ids[1],
            rationale="Senza commi.",
        ),
        [],
    )

    rows = fixture.client.fetch(
        sql.SQL(
            "SELECT l.id, count(cl.article_comma_id) FROM quiz_labelings l "
            "LEFT JOIN quiz_comma_labels cl ON cl.labeling_id = l.id "
            "WHERE l.run_id = %s GROUP BY l.id"
        ),
        [run_id],
    )
    counts = sorted(count for _, count in rows)
    assert counts == [0, 2]

    outcome_columns = fixture.client.fetch(
        sql.SQL(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'quiz_labelings'"
        )
    )
    assert "outcome" not in {row[0] for row in outcome_columns}


@pytest.mark.integration
def test_a_second_run_leaves_the_first_runs_rows_intact(fixture: _Fixture) -> None:
    repository = _make_repository(fixture.client)
    first_run_id = _insert_run(fixture.client)
    repository.insert_labeling(
        QuizLabelingEntity(
            run_id=first_run_id,
            quiz_question_id=fixture.quiz_question_ids[0],
            rationale="Prima motivazione.",
        ),
        [],
    )

    second_run_id = _insert_run(fixture.client)
    repository.insert_labeling(
        QuizLabelingEntity(
            run_id=second_run_id,
            quiz_question_id=fixture.quiz_question_ids[0],
            rationale="Seconda motivazione.",
        ),
        [],
    )

    first_rows = fixture.client.fetch(
        sql.SQL("SELECT rationale FROM quiz_labelings WHERE run_id = %s"),
        [first_run_id],
    )
    second_rows = fixture.client.fetch(
        sql.SQL("SELECT rationale FROM quiz_labelings WHERE run_id = %s"),
        [second_run_id],
    )
    assert first_rows[0][0] == "Prima motivazione."
    assert second_rows[0][0] == "Seconda motivazione."


@pytest.mark.integration
def test_labeling_the_same_question_twice_in_one_run_is_rejected(fixture: _Fixture) -> None:
    run_id = _insert_run(fixture.client)
    repository = _make_repository(fixture.client)
    repository.insert_labeling(
        QuizLabelingEntity(
            run_id=run_id,
            quiz_question_id=fixture.quiz_question_ids[0],
            rationale="Prima.",
        ),
        [],
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        repository.insert_labeling(
            QuizLabelingEntity(
                run_id=run_id,
                quiz_question_id=fixture.quiz_question_ids[0],
                rationale="Seconda.",
            ),
            [],
        )


@pytest.mark.integration
def test_a_label_from_neither_arm_is_rejected_by_the_database(fixture: _Fixture) -> None:
    run_id = _insert_run(fixture.client)
    repository = _make_repository(fixture.client)
    labeling_id = repository.insert_labeling(
        QuizLabelingEntity(
            run_id=run_id,
            quiz_question_id=fixture.quiz_question_ids[0],
            rationale="Motivazione.",
        ),
        [],
    )

    with pytest.raises(psycopg.errors.CheckViolation):
        fixture.client.execute(
            sql.SQL(
                "INSERT INTO quiz_comma_labels "
                "(labeling_id, article_comma_id, judge_rank, dense_rank, text_rank) "
                "VALUES (%s, %s, %s, %s, %s)"
            ),
            [labeling_id, fixture.article_comma_ids[0], 1, None, None],
        )


@pytest.mark.integration
def test_a_failing_child_insert_leaves_no_parent_row(fixture: _Fixture) -> None:
    run_id = _insert_run(fixture.client)
    repository = _make_repository(fixture.client)
    nonexistent_comma_id = max(fixture.article_comma_ids) + 1_000

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repository.insert_labeling(
            QuizLabelingEntity(
                run_id=run_id,
                quiz_question_id=fixture.quiz_question_ids[0],
                rationale="Motivazione.",
            ),
            [
                QuizCommaLabelEntity(
                    article_comma_id=nonexistent_comma_id, judge_rank=1, dense_rank=1
                )
            ],
        )

    surviving_rows = fixture.client.fetch(
        sql.SQL("SELECT id FROM quiz_labelings WHERE quiz_question_id = %s"),
        [fixture.quiz_question_ids[0]],
    )
    assert surviving_rows == []


@pytest.mark.integration
def test_a_duplicate_judge_rank_is_rejected_by_the_database(fixture: _Fixture) -> None:
    run_id = _insert_run(fixture.client)
    repository = _make_repository(fixture.client)
    labeling_id = repository.insert_labeling(
        QuizLabelingEntity(
            run_id=run_id,
            quiz_question_id=fixture.quiz_question_ids[0],
            rationale="Motivazione.",
        ),
        [
            QuizCommaLabelEntity(
                article_comma_id=fixture.article_comma_ids[0], judge_rank=1, dense_rank=1
            )
        ],
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        fixture.client.execute(
            sql.SQL(
                "INSERT INTO quiz_comma_labels "
                "(labeling_id, article_comma_id, judge_rank, dense_rank, text_rank) "
                "VALUES (%s, %s, %s, %s, %s)"
            ),
            [labeling_id, fixture.article_comma_ids[1], 1, 2, None],
        )


@pytest.mark.integration
def test_per_arm_label_counts_are_obtainable_in_one_query(fixture: _Fixture) -> None:
    run_id = _insert_run(fixture.client)
    repository = _make_repository(fixture.client)
    repository.insert_labeling(
        QuizLabelingEntity(
            run_id=run_id,
            quiz_question_id=fixture.quiz_question_ids[0],
            rationale="Motivazione.",
        ),
        [
            QuizCommaLabelEntity(
                article_comma_id=fixture.article_comma_ids[0],
                judge_rank=1,
                dense_rank=1,
                text_rank=None,
            ),
            QuizCommaLabelEntity(
                article_comma_id=fixture.article_comma_ids[1],
                judge_rank=2,
                dense_rank=None,
                text_rank=1,
            ),
            QuizCommaLabelEntity(
                article_comma_id=fixture.article_comma_ids[2],
                judge_rank=3,
                dense_rank=2,
                text_rank=2,
            ),
        ],
    )

    rows = fixture.client.fetch(
        sql.SQL(
            "SELECT "
            "count(*) FILTER (WHERE dense_rank IS NOT NULL AND text_rank IS NULL), "
            "count(*) FILTER (WHERE text_rank IS NOT NULL AND dense_rank IS NULL), "
            "count(*) FILTER (WHERE dense_rank IS NOT NULL AND text_rank IS NOT NULL) "
            "FROM quiz_comma_labels cl JOIN quiz_labelings l ON l.id = cl.labeling_id "
            "WHERE l.run_id = %s"
        ),
        [run_id],
    )
    dense_only, text_only, both_arms = rows[0]
    assert dense_only == 1
    assert text_only == 1
    assert both_arms == 1
