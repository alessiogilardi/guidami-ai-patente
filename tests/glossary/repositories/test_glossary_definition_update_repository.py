import pytest
from glossary.repositories.glossary_definition_update_repository import (
    GlossaryDefinitionUpdateRepository,
)
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig

_EMBEDDING = [0.1] * 1536


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig):
    client = PostgresClient(postgres_test_config)
    client.truncate("glossary_entries")
    yield client
    client.truncate("glossary_entries")
    client.close()


def _seed(client: PostgresClient, term: str) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO glossary_entries "
            "(source, article_number, comma_number, term, definition, embedding_3_small) "
            "VALUES ('cds', '3', '1', %s, 'def', %s::vector) RETURNING id"
        ),
        [term, _EMBEDDING],
    )
    return int(rows[0][0])


def _normalized_rows(client: PostgresClient) -> list[tuple]:
    rows = client.fetch(
        sql.SQL("SELECT term, definition, embedding_3_small FROM glossary_entries")
    )
    return [(term, definition, list(embedding)) for term, definition, embedding in rows]


@pytest.mark.integration
def test_it_updates_only_the_given_ids(
    postgres_test_config: PostgresConnectionConfig, client: PostgresClient
) -> None:
    id_one = _seed(client, "carreggiata")
    id_two = _seed(client, "banchina")
    repository = GlossaryDefinitionUpdateRepository("glossary_entries", client)

    repository.update_many([(id_one, "La parte della strada per i veicoli.")])

    rows = client.fetch(sql.SQL("SELECT id, definition_plain FROM glossary_entries ORDER BY id"))
    assert rows == [(id_one, "La parte della strada per i veicoli."), (id_two, None)]


@pytest.mark.integration
def test_it_touches_no_other_column(
    postgres_test_config: PostgresConnectionConfig, client: PostgresClient
) -> None:
    entry_id = _seed(client, "carreggiata")
    before = _normalized_rows(client)
    repository = GlossaryDefinitionUpdateRepository("glossary_entries", client)

    repository.update_many([(entry_id, "La parte della strada per i veicoli.")])

    after = _normalized_rows(client)
    assert before == after
