"""Unit tests for the auth dependencies against a fake repository (spec 0016, FR-1, FR-3)."""

from dataclasses import dataclass

import pytest

from domain.entities.users import UserEntity
from guidami_ai_patente.exceptions import UnregisteredUserError


@dataclass
class _UserRepositoryDouble:
    entity: UserEntity
    calls: list[int]

    def provision(self, telegram_user_id: int) -> UserEntity:
        self.calls.append(telegram_user_id)
        return self.entity


@pytest.mark.asyncio
async def test_require_registered_user_passes_through_a_registered_caller() -> None:
    from guidami_ai_patente.api.dependencies.user_identity import require_registered_user

    user = await require_registered_user(UserEntity(telegram_user_id=42, registered=True))

    assert user.telegram_user_id == 42


@pytest.mark.asyncio
async def test_require_registered_user_rejects_an_unregistered_caller() -> None:
    from guidami_ai_patente.api.dependencies.user_identity import require_registered_user

    with pytest.raises(UnregisteredUserError):
        await require_registered_user(UserEntity(telegram_user_id=42, registered=False))
