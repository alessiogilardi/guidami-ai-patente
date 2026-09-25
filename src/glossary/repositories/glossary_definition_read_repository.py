from psycopg import sql
from pywire import Autowired, repository

from commons.clients import PostgresClient
from glossary.configs import GlossaryConfig
from glossary.models import GlossaryDefinitionRow


@repository
class GlossaryDefinitionReadRepository:
    """Selects the rows `simplify-glossary-definitions` still needs to simplify (FR-2)."""

    config: Autowired[GlossaryConfig]
    postgres: Autowired[PostgresClient]

    def __init__(
        self, table_name: str | None = None, client: PostgresClient | None = None
    ) -> None:
        """`table_name`/`client` are only ever passed directly in a test."""
        self._explicit_table = table_name
        self._explicit_client = client

    def find_missing_simplifications(self, force: bool) -> list[GlossaryDefinitionRow]:
        """Returns every row needing simplification, or every row when `force` is set."""
        table = self._explicit_table or self.config.glossary_entries_table
        client = self._explicit_client or self.postgres
        where = sql.SQL("") if force else sql.SQL(" WHERE definition_plain IS NULL")
        query = sql.SQL("SELECT id, term, definition FROM {table}{where} ORDER BY id").format(
            table=sql.Identifier(table), where=where
        )
        rows = client.fetch(query)
        return [GlossaryDefinitionRow(id=row[0], term=row[1], definition=row[2]) for row in rows]
