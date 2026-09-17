"""Provisions and reads the Telegram user whitelist."""

from psycopg import sql
from pywire import Autowired, repository

from domain.entities.users import UserEntity
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig


@repository
class UserRepository:
    """Every read/write the auth gate makes against `users` (spec 0016, FR-1).

    Synchronous by construction, like every repository here (AD-10); the routers/
    dependencies cross the boundary with `asyncio.to_thread`.
    """

    config: Autowired[AppConfig]
    postgres: Autowired[PostgresClientProvider]

    def provision(self, telegram_user_id: int) -> UserEntity:
        """Idempotently provisions the row for `telegram_user_id`, then reads it back (FR-1).

        Two statements rather than one `RETURNING`: `ON CONFLICT DO NOTHING` returns
        no row on a conflict, and a follow-up `SELECT` always finds the row regardless
        of which branch fired — atomic at the database level, no application-side
        locking needed (AD-6).
        """
        insert = sql.SQL(
            "INSERT INTO {table} (telegram_user_id) VALUES (%s) "
            "ON CONFLICT (telegram_user_id) DO NOTHING"
        ).format(table=sql.Identifier(self.config.users_table))
        self.postgres.client.execute(insert, [telegram_user_id])

        select = sql.SQL(
            "SELECT telegram_user_id, registered FROM {table} WHERE telegram_user_id = %s"
        ).format(table=sql.Identifier(self.config.users_table))
        rows = self.postgres.client.fetch(select, [telegram_user_id])
        row_telegram_user_id, registered = rows[0]
        return UserEntity(telegram_user_id=int(row_telegram_user_id), registered=bool(registered))
