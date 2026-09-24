import pytest
from glossary.repositories.glossary_entry_read_repository import GlossaryEntryReadRepository
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from glossary.configs import GlossaryBlockConfig


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig):
    client = PostgresClient(postgres_test_config)
    client.truncate("glossary_entries")
    yield client
    client.truncate("glossary_entries")
    client.close()


def _seed(client: PostgresClient, *, article_number: str, comma_number: str, term: str) -> None:
    client.execute(
        sql.SQL(
            "INSERT INTO glossary_entries "
            "(source, article_number, comma_number, term, definition, embedding_3_small) "
            "VALUES ('cds', %s, %s, %s, 'x', %s::vector)"
        ),
        [article_number, comma_number, term, [0.1] * 1536],
    )


@pytest.mark.integration
def test_an_empty_table_reports_no_entries(
    postgres_test_config: PostgresConnectionConfig, client: PostgresClient
) -> None:
    repository = GlossaryEntryReadRepository("glossary_entries", client)
    block = GlossaryBlockConfig(source="cds", file="x.json", article_number="3", comma_number="1")
    assert repository.has_entries_for(block) is False


@pytest.mark.integration
def test_a_seeded_single_comma_block_reports_entries(
    postgres_test_config: PostgresConnectionConfig, client: PostgresClient
) -> None:
    _seed(client, article_number="3", comma_number="1", term="carreggiata")
    repository = GlossaryEntryReadRepository("glossary_entries", client)
    block = GlossaryBlockConfig(source="cds", file="x.json", article_number="3", comma_number="1")
    assert repository.has_entries_for(block) is True


@pytest.mark.integration
def test_a_multi_comma_block_ignores_comma_number_in_the_check(
    postgres_test_config: PostgresConnectionConfig, client: PostgresClient
) -> None:
    _seed(client, article_number="9", comma_number="2", term="alfa")
    repository = GlossaryEntryReadRepository("glossary_entries", client)
    block = GlossaryBlockConfig(source="cds", file="x.json", article_number="9")
    assert repository.has_entries_for(block) is True
