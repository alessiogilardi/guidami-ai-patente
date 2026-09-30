"""Tests for InvalidateStaleLabelingsStep (spec 0023, FR-5) against the ephemeral Postgres."""

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from flowstep import FlowContext
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.quiz import QuizImageEntity
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import InvalidateStaleLabelingsStep
from guidami_ai_patente_ingestor.repositories import QuizLabelingInvalidationRepository

_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
    "quiz_answers",
    "quiz_questions",
    "article_commas",
    "articles",
)


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate(*_TABLES)
        client.truncate("quiz_images")
        yield client
        client.truncate(*_TABLES)
        client.truncate("quiz_images")


def _one(client: PostgresClient, query: str, params: list[object]) -> int:
    return client.fetch(sql.SQL(query), params)[0][0]


def _seed_image(client: PostgresClient, filename: str, description: str | None) -> None:
    client.execute(
        sql.SQL("INSERT INTO quiz_images (filename, description) VALUES (%s, %s)"),
        [filename, description],
    )


def _seed_question(client: PostgresClient, number: str, image: str) -> int:
    return _one(
        client,
        "INSERT INTO quiz_questions (number, question_id, topic, text, correct_answer, "
        "image_filename) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        [number, 1, "segnaletica", f"Domanda {number}?", True, image],
    )


def _seed_run(client: PostgresClient, origin: str) -> int:
    return _one(
        client,
        "INSERT INTO labeling_runs (judge_model, prompt_version, candidate_variant, dense_k, "
        "text_k, lexeme_fields, shuffle_seed, corpus_commit, corpus_comma_count, origin) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        ["judge", "0" * 16, "topic_text", 50, 50, ["topic"], 42, "0" * 40, 1, origin],
    )


def _seed_comma(client: PostgresClient) -> int:
    article_id = _one(
        client,
        "INSERT INTO articles (source, number, title, url, scraped_at) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        ["cds", "1", "Titolo", "https://example.test", datetime.now(UTC)],
    )
    return _one(
        client,
        "INSERT INTO article_commas (article_id, comma_number, position, text, embedding) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        [article_id, "1", 0, "Testo comma.", None],
    )


def _seed_labeling(
    client: PostgresClient, run_id: int, question_id: int, comma_id: int, validated: bool = False
) -> int:
    labeling_id = _one(
        client,
        "INSERT INTO quiz_labelings (run_id, quiz_question_id, rationale, "
        "has_supporting_commas, validated_at, validated_by) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        [
            run_id,
            question_id,
            "Motivazione.",
            True,
            datetime.now(UTC) if validated else None,
            "tester" if validated else None,
        ],
    )
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_comma_labels "
            "(labeling_id, article_comma_id, judge_rank, dense_rank) "
            "VALUES (%s, %s, 1, 1)"
        ),
        [labeling_id, comma_id],
    )
    return labeling_id


def _labeling_count(client: PostgresClient) -> int:
    return _one(client, "SELECT count(*) FROM quiz_labelings", [])


def _comma_label_count(client: PostgresClient) -> int:
    return _one(client, "SELECT count(*) FROM quiz_comma_labels", [])


def _step(client: PostgresClient) -> InvalidateStaleLabelingsStep:
    return InvalidateStaleLabelingsStep(
        "invalidate_stale_labelings",
        QuizLabelingInvalidationRepository(
            "quiz_images", "quiz_questions", "quiz_labelings", client
        ),
    )


def _run(step: InvalidateStaleLabelingsStep, *images: QuizImageEntity) -> None:
    step.execute(FlowContext({context_keys.QUIZ_IMAGE_ENTITIES: list(images)}))


def _image(filename: str, description: str | None) -> QuizImageEntity:
    return QuizImageEntity(filename=filename, description=description)


@pytest.mark.integration
def test_deletes_unvalidated_labelings_of_changed_images_of_every_run_origin(
    client: PostgresClient,
) -> None:
    _seed_image(client, "changed.jpeg", "Vecchia.")
    _seed_image(client, "same.jpeg", "Uguale.")
    comma_id = _seed_comma(client)
    live, batch = _seed_run(client, "live"), _seed_run(client, "batch")
    changed_live = _seed_question(client, "1", "changed.jpeg")
    changed_batch = _seed_question(client, "2", "changed.jpeg")
    unchanged = _seed_question(client, "3", "same.jpeg")
    _seed_labeling(client, live, changed_live, comma_id)
    _seed_labeling(client, batch, changed_batch, comma_id)
    kept = _seed_labeling(client, live, unchanged, comma_id)

    _run(_step(client), _image("changed.jpeg", "Nuova."), _image("same.jpeg", "Uguale."))

    remaining = client.fetch(sql.SQL("SELECT id FROM quiz_labelings"))
    assert remaining == [(kept,)]
    assert _comma_label_count(client) == 1, "comma labels must cascade with their labeling"


@pytest.mark.integration
def test_spares_human_validated_labelings_and_warns(
    client: PostgresClient, caplog: pytest.LogCaptureFixture
) -> None:
    _seed_image(client, "changed.jpeg", "Vecchia.")
    comma_id = _seed_comma(client)
    run = _seed_run(client, "live")
    validated = _seed_labeling(
        client, run, _seed_question(client, "1", "changed.jpeg"), comma_id, True
    )
    _seed_labeling(client, run, _seed_question(client, "2", "changed.jpeg"), comma_id)

    with caplog.at_level(logging.WARNING):
        _run(_step(client), _image("changed.jpeg", "Nuova."))

    assert client.fetch(sql.SQL("SELECT id FROM quiz_labelings")) == [(validated,)]
    assert any("human-validated" in record.getMessage() for record in caplog.records)


@pytest.mark.integration
def test_is_a_noop_when_no_description_changed(client: PostgresClient) -> None:
    _seed_image(client, "same.jpeg", "Uguale.")
    comma_id = _seed_comma(client)
    _seed_labeling(
        client, _seed_run(client, "live"), _seed_question(client, "1", "same.jpeg"), comma_id
    )

    _run(_step(client), _image("same.jpeg", "Uguale."))

    assert _labeling_count(client) == 1


@pytest.mark.integration
def test_a_previously_missing_description_counts_as_changed(client: PostgresClient) -> None:
    _seed_image(client, "was-empty.jpeg", None)
    comma_id = _seed_comma(client)
    _seed_labeling(
        client, _seed_run(client, "live"), _seed_question(client, "1", "was-empty.jpeg"), comma_id
    )

    _run(_step(client), _image("was-empty.jpeg", "Ora c'è."))

    assert _labeling_count(client) == 0


@pytest.mark.integration
def test_a_description_that_disappeared_counts_as_changed(client: PostgresClient) -> None:
    """Review Focus 5: labelings built on a description that no longer exists are stale."""
    _seed_image(client, "lost.jpeg", "C'era.")
    comma_id = _seed_comma(client)
    _seed_labeling(
        client, _seed_run(client, "live"), _seed_question(client, "1", "lost.jpeg"), comma_id
    )

    _run(_step(client), _image("lost.jpeg", None))

    assert _labeling_count(client) == 0


@pytest.mark.integration
def test_rerunning_after_a_failed_store_is_idempotent(client: PostgresClient) -> None:
    """Review Focus 4: the DB still holds the old description, so the change is re-detected."""
    _seed_image(client, "changed.jpeg", "Vecchia.")
    comma_id = _seed_comma(client)
    _seed_labeling(
        client, _seed_run(client, "live"), _seed_question(client, "1", "changed.jpeg"), comma_id
    )
    step = _step(client)

    _run(step, _image("changed.jpeg", "Nuova."))
    _run(step, _image("changed.jpeg", "Nuova."))

    assert _labeling_count(client) == 0


@pytest.mark.integration
def test_duplicate_image_entities_from_shared_images_are_handled(client: PostgresClient) -> None:
    """QUIZ_IMAGE_ENTITIES carries one entry per question, so a shared image repeats."""
    _seed_image(client, "shared.jpeg", "Vecchia.")
    comma_id = _seed_comma(client)
    _seed_labeling(
        client, _seed_run(client, "live"), _seed_question(client, "1", "shared.jpeg"), comma_id
    )
    entity = _image("shared.jpeg", "Nuova.")

    _run(_step(client), entity, entity, entity)

    assert _labeling_count(client) == 0
