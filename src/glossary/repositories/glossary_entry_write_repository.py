from collections.abc import Sequence

from psycopg import sql
from pywire import Autowired, repository

from commons.clients import PostgresClient
from domain.entities.glossary import GlossaryEntryEntity
from glossary.configs import GlossaryBlockConfig, GlossaryConfig

_COLUMNS = ("source", "article_number", "comma_number", "term", "definition")


@repository
class GlossaryEntryWriteRepository:
    """Upserts one block's entries, then reconciles stale ones, scoped to it (FR-6).

    The order matters: a failure between the upsert and the delete leaves at worst a
    few stale extra rows, never an empty block — a rerun converges either way.
    """

    config: Autowired[GlossaryConfig]
    postgres: Autowired[PostgresClient]

    def __init__(
        self,
        table_name: str | None = None,
        client: PostgresClient | None = None,
        embedding_column: str | None = None,
    ) -> None:
        """`table_name`/`client`/`embedding_column` are only ever passed directly in a test."""
        self._explicit_table = table_name
        self._explicit_client = client
        self._explicit_embedding_column = embedding_column

    def write(self, block: GlossaryBlockConfig, entries: Sequence[GlossaryEntryEntity]) -> None:
        """Upserts `entries` for `block`, then deletes any of `block`'s rows not in `entries`."""
        table = self._explicit_table or self.config.glossary_entries_table
        client = self._explicit_client or self.postgres

        if entries:
            self._upsert(table, client, entries)
        self._delete_missing(table, client, block, {entry.term for entry in entries})

    def _upsert(
        self, table: str, client: PostgresClient, entries: Sequence[GlossaryEntryEntity]
    ) -> None:
        # term_ru and definition_plain are always reset to NULL on conflict (FR-6/AD-11,
        # spec 0022 FR-1a): build-glossary never translates or simplifies, so a rebuilt
        # row must not keep a stale prior translation or plain-language rendering tied
        # to a definition that may have changed.
        # The embedding column itself is parametric (AD-4): a new embedding model is
        # a new embedding_* column, chosen via GlossaryConfig.embedding_column, never
        # a literal in this query.
        embedding_column = self._explicit_embedding_column or self.config.embedding_column
        query = sql.SQL(
            "INSERT INTO {table} ({columns}, {embedding_column}) "
            "VALUES ({placeholders}, %s::vector) "
            "ON CONFLICT (source, article_number, comma_number, term) "
            "DO UPDATE SET definition = EXCLUDED.definition, "
            "{embedding_column} = EXCLUDED.{embedding_column}, "
            "term_ru = NULL, definition_plain = NULL"
        ).format(
            table=sql.Identifier(table),
            columns=sql.SQL(", ").join(sql.Identifier(c) for c in _COLUMNS),
            placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in _COLUMNS),
            embedding_column=sql.Identifier(embedding_column),
        )
        client.execute_many(
            query,
            [
                [
                    entry.source,
                    entry.article_number,
                    entry.comma_number,
                    entry.term,
                    entry.definition,
                    entry.embedding,
                ]
                for entry in entries
            ],
        )

    def _delete_missing(
        self,
        table: str,
        client: PostgresClient,
        block: GlossaryBlockConfig,
        present_terms: set[str],
    ) -> None:
        conditions = [sql.SQL("source = %s"), sql.SQL("article_number = %s")]
        params: list[object] = [block.source, block.article_number]
        if block.comma_number is not None:
            conditions.append(sql.SQL("comma_number = %s"))
            params.append(block.comma_number)
        conditions.append(sql.SQL("term <> ALL(%s::text[])"))
        params.append(list(present_terms))

        query = sql.SQL("DELETE FROM {table} WHERE {where}").format(
            table=sql.Identifier(table), where=sql.SQL(" AND ").join(conditions)
        )
        client.execute(query, params)
