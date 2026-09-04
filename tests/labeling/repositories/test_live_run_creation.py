"""One live run per configuration epoch, created lazily and race-safely (FR-9, AD-8)."""

from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.evaluation import LabelingRunEntity
from domain.enums import LabelingRunOrigin
from labeling.repositories import GoldenSetWriteRepository

_TABLES = ("quiz_comma_labels", "quiz_labelings", "labeling_runs")


def _live_run(**overrides: object) -> LabelingRunEntity:
    fields: dict[str, object] = {
        "judge_model": "openrouter/google/gemini-2.5-flash-lite",
        "prompt_version": "0123456789abcdef",
        "candidate_variant": "topic_text",
        "dense_k": 50,
        "text_k": 50,
        "lexeme_fields": ("image_description", "text", "topic"),
        "shuffle_seed": 42,
        "corpus_comma_count": 3,
        "origin": LabelingRunOrigin.LIVE,
    }
    fields.update(overrides)
    return LabelingRunEntity(**fields)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def repository(
    postgres_test_config: PostgresConnectionConfig,
) -> Iterator[tuple[GoldenSetWriteRepository, PostgresClient]]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate(*_TABLES)
        yield (
            GoldenSetWriteRepository(
                "labeling_runs", "quiz_labelings", "quiz_comma_labels", client
            ),
            client,
        )
        client.truncate(*_TABLES)


def _run_count(client: PostgresClient) -> int:
    return int(client.fetch(sql.SQL("SELECT count(*) FROM labeling_runs"))[0][0])


@pytest.mark.integration
def test_the_first_call_creates_the_run(
    repository: tuple[GoldenSetWriteRepository, PostgresClient],
) -> None:
    golden_set, client = repository

    run_id = golden_set.find_or_create_live_run(_live_run())

    assert run_id > 0
    assert _run_count(client) == 1


@pytest.mark.integration
def test_a_second_call_reuses_it(
    repository: tuple[GoldenSetWriteRepository, PostgresClient],
) -> None:
    """The losing racer of AD-19's concurrent case takes exactly this path."""
    golden_set, client = repository

    first = golden_set.find_or_create_live_run(_live_run())
    second = golden_set.find_or_create_live_run(_live_run())

    assert first == second
    assert _run_count(client) == 1


@pytest.mark.integration
def test_run_mechanics_outside_the_epoch_do_not_open_a_new_run(
    repository: tuple[GoldenSetWriteRepository, PostgresClient],
) -> None:
    """`shuffle_seed` is provenance, not identity (AD-8): it is not in the unique index."""
    golden_set, client = repository

    first = golden_set.find_or_create_live_run(_live_run())
    second = golden_set.find_or_create_live_run(_live_run(shuffle_seed=7))

    assert first == second
    assert _run_count(client) == 1


@pytest.mark.integration
def test_a_changed_judge_model_opens_a_second_run(
    repository: tuple[GoldenSetWriteRepository, PostgresClient],
) -> None:
    """A model change opens a new epoch, which is what invalidates the cache (AD-8)."""
    golden_set, client = repository

    first = golden_set.find_or_create_live_run(_live_run())
    second = golden_set.find_or_create_live_run(_live_run(judge_model="other/model"))

    assert first != second
    assert _run_count(client) == 2


@pytest.mark.integration
def test_a_batch_run_is_refused(
    repository: tuple[GoldenSetWriteRepository, PostgresClient],
) -> None:
    """The partial index only covers live rows.

    A batch entity here would insert an unbounded duplicate on every call — refuse it
    explicitly instead.
    """
    golden_set, _ = repository

    with pytest.raises(ValueError, match="origin"):
        golden_set.find_or_create_live_run(
            _live_run(origin=LabelingRunOrigin.BATCH, corpus_commit="deadbeef")
        )
