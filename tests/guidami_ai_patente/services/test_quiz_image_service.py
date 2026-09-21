"""FR-12: the database authorises the filename before the filesystem is touched."""

from collections.abc import Iterator

import pytest
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.exceptions import QuizImageNotFoundError
from guidami_ai_patente.services import QuizImageService

_REFERENCED = "000b9ec4803628ffc83403efb710b16e.jpeg"


@pytest.fixture
def bank_with_image(api_client: object) -> Iterator[PostgresClient]:
    """A single question referencing a real file in the committed image directory."""
    client = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(
        "quiz_comma_labels",
        "quiz_labelings",
        "labeling_runs",
        "quiz_question_embeddings",
        "quiz_answers",
        "quiz_questions",
    )
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_questions "
            "(number, question_id, topic, text, correct_answer, image_filename) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        ),
        ["0001", 1, "segnaletica", "Domanda?", True, _REFERENCED],
    )
    yield client
    client.truncate(
        "quiz_comma_labels",
        "quiz_labelings",
        "labeling_runs",
        "quiz_question_embeddings",
        "quiz_answers",
        "quiz_questions",
    )


@pytest.fixture
def image_service(api_client: object) -> QuizImageService:
    return get_default_container().resolve(QuizImageService)


@pytest.mark.integration
def test_a_referenced_image_is_served_with_its_media_type(
    bank_with_image: PostgresClient, image_service: QuizImageService, app_config: AppConfig
) -> None:
    image = image_service(_REFERENCED)

    assert image.media_type == "image/jpeg"
    assert image.content == (app_config.quiz_images_dir / _REFERENCED).read_bytes()


@pytest.mark.integration
def test_an_unreferenced_name_is_rejected_even_when_the_file_exists(
    bank_with_image: PostgresClient, image_service: QuizImageService, app_config: AppConfig
) -> None:
    existing_but_unreferenced = next(
        path.name
        for path in sorted(app_config.quiz_images_dir.iterdir())
        if path.name != _REFERENCED
    )

    with pytest.raises(QuizImageNotFoundError):
        image_service(existing_but_unreferenced)


@pytest.mark.integration
@pytest.mark.parametrize("attempt", ["../../.env", "../.env", "sub/dir.png", "..\\..\\.env", ""])
def test_a_traversal_attempt_is_rejected_without_touching_the_filesystem(
    bank_with_image: PostgresClient, image_service: QuizImageService, attempt: str
) -> None:
    with pytest.raises(QuizImageNotFoundError):
        image_service(attempt)


@pytest.mark.integration
def test_a_referenced_row_whose_file_is_missing_is_a_404(
    bank_with_image: PostgresClient, image_service: QuizImageService
) -> None:
    bank_with_image.execute(
        sql.SQL("UPDATE quiz_questions SET image_filename = %s WHERE number = %s"),
        ["absent-from-disk.jpeg", "0001"],
    )

    with pytest.raises(QuizImageNotFoundError):
        image_service("absent-from-disk.jpeg")
