"""QuizAnswerCheckRequest is a frozen carrier of the check UseCase's two inputs."""

import pytest

from guidami_ai_patente.models import QuizAnswerCheckRequest


def test_it_is_frozen() -> None:
    request = QuizAnswerCheckRequest(number="0001", submitted_answer=True)

    with pytest.raises(Exception):  # noqa: B017 — pydantic's own frozen-instance error
        request.number = "0002"  # type: ignore[misc]
