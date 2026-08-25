"""Integration tests for the pooled PostgresClient (spec 0012, AD-26)."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import psycopg
import psycopg_pool
import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        yield client


@pytest.mark.integration
def test_concurrent_fetches_do_not_serialise_on_one_connection(
    postgres_test_config: PostgresConnectionConfig,
) -> None:
    config = postgres_test_config.model_copy(update={"pool_min_size": 4, "pool_max_size": 4})
    with PostgresClient(config) as client, ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(client.fetch, sql.SQL("SELECT pg_backend_pid()")) for _ in range(4)]
        pids = {future.result()[0][0] for future in futures}

    assert len(pids) > 1, "every query ran on the same backend: the pool is not pooling"


@pytest.mark.integration
def test_the_pgvector_adapter_is_registered_on_every_pooled_connection(
    postgres_test_config: PostgresConnectionConfig,
) -> None:
    config = postgres_test_config.model_copy(update={"pool_min_size": 3, "pool_max_size": 3})
    with PostgresClient(config) as client, ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(
                client.fetch,
                sql.SQL("SELECT %s::vector"),
                [[0.5, 0.25, 0.125]],
            )
            for _ in range(3)
        ]
        results = [future.result()[0][0] for future in futures]

    assert all(list(result) == [0.5, 0.25, 0.125] for result in results)


@pytest.mark.integration
def test_an_unreachable_database_fails_at_construction_not_at_first_query(
    postgres_test_config: PostgresConnectionConfig,
) -> None:
    """D3: preserves the single-connection failure mode `ingest status --online` relies on."""
    dead = postgres_test_config.model_copy(update={"port": 1, "connect_timeout": 2})

    with pytest.raises(psycopg.Error):
        PostgresClient(dead)


def test_pool_failures_are_catchable_as_psycopg_errors() -> None:
    """D12: `status.py:31` and `prepare.py:133` both catch broad `psycopg.Error`.

    If `PoolTimeout` ever stops subclassing it, an unreachable database stops being
    reported as "unreachable" and crashes with a traceback instead. Pinned here rather
    than discovered at Task 11.
    """
    assert issubclass(psycopg_pool.PoolTimeout, psycopg.Error)
    assert issubclass(psycopg_pool.PoolClosed, psycopg.Error)


@pytest.mark.integration
def test_statements_are_committed_without_an_explicit_transaction(client: PostgresClient) -> None:
    # D4: no CREATE TEMP TABLE probe here — it asserted nothing and returned a
    # connection to the pool carrying a temp table.
    client.execute(sql.SQL("DROP TABLE IF EXISTS _pooled_probe"))
    client.execute(sql.SQL("CREATE TABLE _pooled_probe (v INT)"))
    client.execute(sql.SQL("INSERT INTO _pooled_probe (v) VALUES (%s)"), [7])

    rows = client.fetch(sql.SQL("SELECT v FROM _pooled_probe"))
    client.execute(sql.SQL("DROP TABLE _pooled_probe"))

    assert rows == [(7,)]
