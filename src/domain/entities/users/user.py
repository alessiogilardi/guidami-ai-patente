"""Row of the `users` table (see db/init.sql, spec 0016 AD-2)."""

from pydantic import BaseModel


class UserEntity(BaseModel):
    """A Telegram user's whitelist status.

    `id`/`created_at` are DB-generated (`BIGSERIAL`/`DEFAULT now()`) and have no
    corresponding field here, per the project's entities convention.
    """

    telegram_user_id: int
    registered: bool
