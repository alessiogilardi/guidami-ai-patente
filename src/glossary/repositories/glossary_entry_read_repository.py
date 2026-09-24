from psycopg import sql
from pywire import Autowired, repository

from commons.clients import PostgresClient
from glossary.configs import GlossaryBlockConfig, GlossaryConfig


@repository
class GlossaryEntryReadRepository:
    """The single "is this block already built?" check `build-glossary` needs (FR-2)."""

    config: Autowired[GlossaryConfig]
    postgres: Autowired[PostgresClient]

    def __init__(
        self, table_name: str | None = None, client: PostgresClient | None = None
    ) -> None:
        """`table_name`/`client` are only ever passed directly in a test."""
        self._explicit_table = table_name
        self._explicit_client = client

    def has_entries_for(self, block: GlossaryBlockConfig) -> bool:
        """Whether `glossary_entries` already holds a row for `block`.

        Filters on `comma_number` only when the block names one — a block spanning
        every comma of an article is "already built" once any of its entries exist.
        """
        table = self._explicit_table or self.config.glossary_entries_table
        client = self._explicit_client or self.postgres
        conditions = [sql.SQL("source = %s"), sql.SQL("article_number = %s")]
        params: list[object] = [block.source, block.article_number]
        if block.comma_number is not None:
            conditions.append(sql.SQL("comma_number = %s"))
            params.append(block.comma_number)

        query = sql.SQL("SELECT EXISTS(SELECT 1 FROM {table} WHERE {where})").format(
            table=sql.Identifier(table), where=sql.SQL(" AND ").join(conditions)
        )
        rows = client.fetch(query, params)
        return bool(rows[0][0])
