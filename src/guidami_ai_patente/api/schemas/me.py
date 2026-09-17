"""Response schema for GET /me."""

from pydantic import BaseModel


class MeResponse(BaseModel):
    """Whether the calling Telegram user is approved to use the bot (FR-2)."""

    registered: bool
