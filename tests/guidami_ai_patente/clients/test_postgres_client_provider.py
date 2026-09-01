"""The pooled connection is one container-managed singleton (spec 0012, AD-16, AD-26)."""

from dataclasses import dataclass

import pytest
from psycopg import sql
from pywire import get_default_container
from pywire.lifecycle import find_pre_destroy

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider


@dataclass
class _FakePostgresClient:
    closed: bool = False

    def close(self) -> None:
        self.closed = True


def test_closing_the_provider_closes_its_client() -> None:
    provider = object.__new__(PostgresClientProvider)
    fake_client = _FakePostgresClient()
    provider.client = fake_client  # type: ignore[assignment]

    pre_destroy = find_pre_destroy(PostgresClientProvider)
    assert pre_destroy is not None, "PostgresClientProvider must declare a @pre_destroy method"
    _, teardown = pre_destroy
    teardown(provider)

    assert fake_client.closed is True


@pytest.mark.integration
def test_the_provider_exposes_a_usable_pooled_client(api_client: object) -> None:
    provider = get_default_container().resolve(PostgresClientProvider)

    assert isinstance(provider.client, PostgresClient)
    assert provider.client.fetch(sql.SQL("SELECT 1")) == [(1,)]


@pytest.mark.integration
def test_every_consumer_shares_one_client(api_client: object) -> None:
    container = get_default_container()

    assert container.resolve(PostgresClientProvider).client is (
        container.resolve(PostgresClientProvider).client
    )


@pytest.mark.integration
def test_closing_the_real_container_does_not_raise(api_client: object) -> None:
    get_default_container().resolve(PostgresClientProvider)

    get_default_container().close()
