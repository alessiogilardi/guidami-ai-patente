import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.glossary import GlossaryEntryEntity
from glossary.configs import GlossaryBlockConfig
from glossary.repositories.glossary_entry_write_repository import GlossaryEntryWriteRepository

_EMBEDDING = [0.1] * 1536


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig):
    client = PostgresClient(postgres_test_config)
    client.truncate("glossary_entries")
    yield client
    client.truncate("glossary_entries")
    client.close()


def _entity(term: str, comma_number: str = "1") -> GlossaryEntryEntity:
    return GlossaryEntryEntity(
        source="cds",
        article_number="3",
        comma_number=comma_number,
        term=term,
        definition=f"Definizione di {term}.",
        term_ru=None,
        embedding=_EMBEDDING,
    )


def _rows(client: PostgresClient) -> list[tuple]:
    return client.fetch(
        sql.SQL(
            "SELECT term, term_ru FROM glossary_entries WHERE article_number = '3' ORDER BY term"
        )
    )


@pytest.mark.integration
def test_it_inserts_new_entries_with_term_ru_null(
    postgres_test_config: PostgresConnectionConfig, client: PostgresClient
) -> None:
    repository = GlossaryEntryWriteRepository("glossary_entries", client, "embedding_3_small")
    block = GlossaryBlockConfig(source="cds", file="x.json", article_number="3", comma_number="1")

    repository.write(block, [_entity("carreggiata")])

    assert _rows(client) == [("carreggiata", None)]


@pytest.mark.integration
def test_a_rebuild_resets_term_ru_to_null(
    postgres_test_config: PostgresConnectionConfig, client: PostgresClient
) -> None:
    repository = GlossaryEntryWriteRepository("glossary_entries", client, "embedding_3_small")
    block = GlossaryBlockConfig(source="cds", file="x.json", article_number="3", comma_number="1")
    repository.write(block, [_entity("carreggiata")])
    client.execute(sql.SQL("UPDATE glossary_entries SET term_ru = 'проезжая часть'"))

    repository.write(block, [_entity("carreggiata")])

    assert _rows(client) == [("carreggiata", None)]


@pytest.mark.integration
def test_reconciliation_deletes_only_this_blocks_stale_entries(
    postgres_test_config: PostgresConnectionConfig, client: PostgresClient
) -> None:
    repository = GlossaryEntryWriteRepository("glossary_entries", client, "embedding_3_small")
    block = GlossaryBlockConfig(source="cds", file="x.json", article_number="3", comma_number="1")
    other_block = GlossaryBlockConfig(
        source="cds", file="x.json", article_number="157", comma_number="1"
    )
    repository.write(block, [_entity("carreggiata"), _entity("banchina")])
    repository.write(
        other_block,
        [
            GlossaryEntryEntity(
                source="cds",
                article_number="157",
                comma_number="1",
                term="arresto",
                definition="Definizione di arresto.",
                term_ru=None,
                embedding=_EMBEDDING,
            )
        ],
    )

    repository.write(block, [_entity("carreggiata")])

    assert _rows(client) == [("carreggiata", None)]
    other_rows = client.fetch(
        sql.SQL("SELECT term FROM glossary_entries WHERE article_number = '157'")
    )
    assert other_rows == [("arresto",)]


@pytest.mark.integration
def test_embedding_3_small_round_trips_as_a_1536_dimension_vector(
    postgres_test_config: PostgresConnectionConfig, client: PostgresClient
) -> None:
    repository = GlossaryEntryWriteRepository("glossary_entries", client, "embedding_3_small")
    block = GlossaryBlockConfig(source="cds", file="x.json", article_number="3", comma_number="1")

    repository.write(block, [_entity("carreggiata")])

    rows = client.fetch(sql.SQL("SELECT embedding_3_small FROM glossary_entries"))
    assert len(rows[0][0]) == 1536


@pytest.mark.integration
def test_tsv_term_matches_an_inflected_form(
    postgres_test_config: PostgresConnectionConfig, client: PostgresClient
) -> None:
    repository = GlossaryEntryWriteRepository("glossary_entries", client, "embedding_3_small")
    block = GlossaryBlockConfig(source="cds", file="x.json", article_number="3", comma_number="1")

    repository.write(block, [_entity("carreggiata")])

    rows = client.fetch(
        sql.SQL(
            "SELECT term FROM glossary_entries "
            "WHERE tsv_term @@ to_tsquery('italian', 'carreggiate')"
        )
    )
    assert rows == [("carreggiata",)]
