from collections.abc import Sequence

from psycopg import sql
from pywire import Autowired, repository

from commons.clients import PostgresClient
from glossary.configs import GlossaryConfig


@repository
class GlossaryTermUpdateRepository:
    """The only class that ever writes `term_ru` (FR-5, AD-11)."""

    config: Autowired[GlossaryConfig]
    postgres: Autowired[PostgresClient]

    def __init__(
        self, table_name: str | None = None, client: PostgresClient | None = None
    ) -> None:
        """`table_name`/`client` are only ever passed directly in a test."""
        self._explicit_table = table_name
        self._explicit_client = client

    def update_many(self, translations: Sequence[tuple[int, str]]) -> None:
        """Updates `term_ru` for exactly the given `(id, term_ru)` pairs."""
        if not translations:
            return
        table = self._explicit_table or self.config.glossary_entries_table
        client = self._explicit_client or self.postgres
        query = sql.SQL("UPDATE {table} SET term_ru = %s WHERE id = %s").format(
            table=sql.Identifier(table)
        )
        client.execute_many(query, [(term_ru, entry_id) for entry_id, term_ru in translations])
