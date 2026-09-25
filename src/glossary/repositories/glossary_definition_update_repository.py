from collections.abc import Sequence

from psycopg import sql
from pywire import Autowired, repository

from commons.clients import PostgresClient
from glossary.configs import GlossaryConfig


@repository
class GlossaryDefinitionUpdateRepository:
    """The only class that ever writes `definition_plain` (FR-2, spec 0022)."""

    config: Autowired[GlossaryConfig]
    postgres: Autowired[PostgresClient]

    def __init__(
        self, table_name: str | None = None, client: PostgresClient | None = None
    ) -> None:
        """`table_name`/`client` are only ever passed directly in a test."""
        self._explicit_table = table_name
        self._explicit_client = client

    def update_many(self, simplifications: Sequence[tuple[int, str]]) -> None:
        """Updates `definition_plain` for exactly the given `(id, definition_plain)` pairs."""
        if not simplifications:
            return
        table = self._explicit_table or self.config.glossary_entries_table
        client = self._explicit_client or self.postgres
        query = sql.SQL("UPDATE {table} SET definition_plain = %s WHERE id = %s").format(
            table=sql.Identifier(table)
        )
        client.execute_many(
            query, [(definition_plain, entry_id) for entry_id, definition_plain in simplifications]
        )
