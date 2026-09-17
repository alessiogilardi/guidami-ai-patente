"""QuizAnswerCheckRequest is a frozen carrier of the check UseCase's inputs."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente.models import QuizAnswerCheckRequest


def test_it_is_frozen() -> None:
    request = QuizAnswerCheckRequest(
        number="0001", submitted_answer=True, session_id="seed-abc", telegram_user_id=42
    )

    with pytest.raises(ValidationError):
        request.number = "0002"  # type: ignore[misc]
