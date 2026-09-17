"""Raised when a caller's `users` row exists but is not yet approved."""

from .guidami_api_error import GuidamiApiError


class UnregisteredUserError(GuidamiApiError):
    """The caller's `telegram_user_id` resolves to a `users` row with `registered = false`.

    Raised by `require_registered_user` (spec 0016, FR-3, AD-4) after the base identity
    step has already provisioned the row — never before, so an unregistered caller is
    always visible for manual approval (FR-1's second acceptance criterion).
    """

    def __init__(self, telegram_user_id: int) -> None:
        """Builds the error for the given Telegram user id."""
        super().__init__(f"Telegram user {telegram_user_id} is not yet approved.")
