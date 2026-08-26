"""The pooled connection is one container-managed singleton (spec 0012, AD-16, AD-26)."""

import pytest
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider


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
