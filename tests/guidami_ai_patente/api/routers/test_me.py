"""End-to-end tests for GET /me (spec 0016, FR-1, FR-2)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider

_TABLES = ("quiz_answers", "users")


@pytest.fixture
def clean_users(api_client: TestClient) -> Iterator[PostgresClient]:
    client = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(*_TABLES)
    yield client
    client.truncate(*_TABLES)


@pytest.mark.integration
def test_an_unknown_caller_is_reported_as_unregistered_and_provisioned(
    clean_users: PostgresClient, api_client: TestClient
) -> None:
    response = api_client.get("/me", headers={"X-Telegram-User-Id": "42"})

    assert response.status_code == 200
    assert response.json() == {"registered": False}
    row = clean_users.fetch(
        sql.SQL("SELECT registered FROM users WHERE telegram_user_id = %s"), [42]
    )
    assert row == [(False,)]


@pytest.mark.integration
def test_a_registered_caller_is_reported_as_registered(
    clean_users: PostgresClient, api_client: TestClient
) -> None:
    clean_users.execute(
        sql.SQL("INSERT INTO users (telegram_user_id, registered) VALUES (%s, true)"), [7]
    )

    response = api_client.get("/me", headers={"X-Telegram-User-Id": "7"})

    assert response.json() == {"registered": True}


@pytest.mark.integration
def test_me_never_rejects_an_unregistered_caller(
    clean_users: PostgresClient, api_client: TestClient
) -> None:
    response = api_client.get("/me", headers={"X-Telegram-User-Id": "999"})

    assert response.status_code == 200
