"""Integration tests for FR-8's precedence rule and FR-14's version probe."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.providers import LabelingStackProvider
from guidami_ai_patente.repositories import GoldenSetReadRepository
from labeling.models import LabelingEpoch

_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
    "quiz_answers",
    "quiz_questions",
)


def _insert_run(client: PostgresClient, epoch: LabelingEpoch, origin: str) -> int:
    """Inserts a run carrying exactly `epoch`, so a read filtered by it matches."""
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO labeling_runs "
            "(judge_model, prompt_version, candidate_variant, dense_k, text_k, "
            " lexeme_fields, shuffle_seed, corpus_commit, corpus_comma_count, origin) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"
        ),
        [
            epoch.judge_model,
            epoch.prompt_version,
            epoch.candidate_variant,
            epoch.dense_k,
            epoch.text_k,
            list(epoch.lexeme_fields),
            42,
            "deadbeef" if origin == "batch" else None,
            3,
            origin,
        ],
    )
    return int(rows[0][0])


def _insert_labeling(
    client: PostgresClient,
    run_id: int,
    question_id: int,
    rationale: str,
    *,
    has_commas: bool,
    validated: bool = False,
    created_at: datetime | None = None,
) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO quiz_labelings "
            "(run_id, quiz_question_id, rationale, has_supporting_commas, "
            " validated_at, validated_by, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, now())) RETURNING id"
        ),
        [
            run_id,
            question_id,
            rationale,
            has_commas,
            datetime.now(UTC) if validated else None,
            "alessio" if validated else None,
            created_at,
        ],
    )
    return int(rows[0][0])


@pytest.fixture
def golden_set(api_client: object) -> Iterator[tuple[PostgresClient, int, LabelingEpoch]]:
    """One question on the ephemeral stack plus the app's own resolved epoch."""
    container = get_default_container()
    client = container.resolve(PostgresClientProvider).client
    epoch = container.resolve(LabelingStackProvider).epoch
    client.truncate(*_TABLES)
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO quiz_questions (number, question_id, topic, text, correct_answer) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        ["0001", 1, "velocità", "Domanda?", True],
    )
    yield client, int(rows[0][0]), epoch
    client.truncate(*_TABLES)


@pytest.fixture
def repository(api_client: object) -> GoldenSetReadRepository:
    return get_default_container().resolve(GoldenSetReadRepository)


@pytest.mark.integration
def test_no_labeling_at_all_is_a_cache_miss(
    golden_set: tuple[PostgresClient, int, LabelingEpoch],
    repository: GoldenSetReadRepository,
) -> None:
    _, _, epoch = golden_set
    assert repository.find_current_labeling("0001", epoch) is None


@pytest.mark.integration
def test_a_matching_run_labeling_is_current(
    golden_set: tuple[PostgresClient, int, LabelingEpoch],
    repository: GoldenSetReadRepository,
) -> None:
    client, question_id, epoch = golden_set
    run_id = _insert_run(client, epoch, "batch")
    _insert_labeling(client, run_id, question_id, "trovato", has_commas=True)

    current = repository.find_current_labeling("0001", epoch)

    assert current is not None
    assert (current.rationale, current.has_supporting_commas, current.origin) == (
        "trovato",
        True,
        "batch",
    )


@pytest.mark.integration
def test_a_human_validated_labeling_wins_over_a_matching_run(
    golden_set: tuple[PostgresClient, int, LabelingEpoch],
    repository: GoldenSetReadRepository,
) -> None:
    client, question_id, epoch = golden_set
    outdated = _insert_run(client, epoch.model_copy(update={"judge_model": "old/model"}), "batch")
    current_run = _insert_run(client, epoch, "batch")
    _insert_labeling(
        client, outdated, question_id, "validato a mano", has_commas=True, validated=True
    )
    _insert_labeling(client, current_run, question_id, "automatico", has_commas=True)

    current = repository.find_current_labeling("0001", epoch)

    assert current is not None
    assert (current.rationale, current.human_validated) == ("validato a mano", True)


@pytest.mark.integration
def test_the_most_recent_matching_labeling_wins(
    golden_set: tuple[PostgresClient, int, LabelingEpoch],
    repository: GoldenSetReadRepository,
) -> None:
    client, question_id, epoch = golden_set
    older_run = _insert_run(client, epoch, "batch")
    newer_run = _insert_run(client, epoch, "live")
    _insert_labeling(
        client,
        older_run,
        question_id,
        "vecchia",
        has_commas=True,
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    _insert_labeling(
        client,
        newer_run,
        question_id,
        "nuova",
        has_commas=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    current = repository.find_current_labeling("0001", epoch)

    assert current is not None
    assert current.rationale == "nuova"


@pytest.mark.integration
def test_a_labeling_from_another_epoch_is_not_current(
    golden_set: tuple[PostgresClient, int, LabelingEpoch],
    repository: GoldenSetReadRepository,
) -> None:
    client, question_id, epoch = golden_set
    stale = _insert_run(client, epoch.model_copy(update={"dense_k": epoch.dense_k + 1}), "batch")
    _insert_labeling(client, stale, question_id, "altra epoca", has_commas=True)

    assert repository.find_current_labeling("0001", epoch) is None


@pytest.mark.integration
def test_reordered_lexeme_fields_are_the_same_epoch(
    golden_set: tuple[PostgresClient, int, LabelingEpoch],
    repository: GoldenSetReadRepository,
) -> None:
    """AD-8: the value is canonicalised by sorting on write, so order never forks the epoch."""
    client, question_id, epoch = golden_set
    run_id = _insert_run(client, epoch, "batch")
    _insert_labeling(client, run_id, question_id, "ordinata", has_commas=True)

    reordered = list(reversed(epoch.lexeme_fields))
    client.execute(
        sql.SQL("UPDATE labeling_runs SET lexeme_fields = %s WHERE id = %s"),
        [reordered, run_id],
    )

    assert repository.find_current_labeling("0001", epoch) is None, (
        "a run written with an unsorted array is out of epoch by construction — which "
        "is why AD-8 canonicalises on write rather than normalising on read"
    )


@pytest.mark.integration
def test_the_empty_verdict_is_still_a_current_labeling(
    golden_set: tuple[PostgresClient, int, LabelingEpoch],
    repository: GoldenSetReadRepository,
) -> None:
    client, question_id, epoch = golden_set
    run_id = _insert_run(client, epoch, "batch")
    _insert_labeling(client, run_id, question_id, "nessun comma", has_commas=False)

    current = repository.find_current_labeling("0001", epoch)

    assert current is not None
    assert current.has_supporting_commas is False


@pytest.mark.integration
def test_distinct_prompt_versions_are_listed(
    golden_set: tuple[PostgresClient, int, LabelingEpoch],
    repository: GoldenSetReadRepository,
) -> None:
    client, _, epoch = golden_set
    _insert_run(client, epoch, "batch")
    _insert_run(client, epoch.model_copy(update={"prompt_version": "ffffffffffffffff"}), "batch")

    assert sorted(repository.distinct_prompt_versions()) == sorted(
        {epoch.prompt_version, "ffffffffffffffff"}
    )


@pytest.mark.integration
def test_an_empty_golden_set_lists_no_versions(
    golden_set: tuple[PostgresClient, int, LabelingEpoch],
    repository: GoldenSetReadRepository,
) -> None:
    assert repository.distinct_prompt_versions() == []
