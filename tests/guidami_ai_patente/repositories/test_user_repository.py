"""Integration tests for the `users` provisioning repository (spec 0016, FR-1)."""

from collections.abc import Iterator

import pytest
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.repositories import UserRepository

_TABLES = ("quiz_answers", "users")


@pytest.fixture
def clean_users(api_client: object) -> Iterator[PostgresClient]:
    client = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(*_TABLES)
    yield client
    client.truncate(*_TABLES)


@pytest.fixture
def repository(api_client: object) -> UserRepository:
    return get_default_container().resolve(UserRepository)


@pytest.mark.integration
def test_a_first_contact_creates_an_unregistered_row(
    clean_users: PostgresClient, repository: UserRepository
) -> None:
    user = repository.provision(42)

    assert user.telegram_user_id == 42
    assert user.registered is False


@pytest.mark.integration
def test_a_second_contact_does_not_reset_an_already_registered_row(
    clean_users: PostgresClient, repository: UserRepository
) -> None:
    repository.provision(42)
    clean_users.execute(
        sql.SQL("UPDATE users SET registered = true WHERE telegram_user_id = %s"), [42]
    )

    user = repository.provision(42)

    assert user.registered is True


@pytest.mark.integration
def test_a_second_contact_leaves_an_unregistered_row_unregistered(
    clean_users: PostgresClient, repository: UserRepository
) -> None:
    repository.provision(42)

    user = repository.provision(42)

    assert user.registered is False
