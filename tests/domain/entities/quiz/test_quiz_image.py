from domain.entities.quiz import QuizImageEntity


def test_construct_with_filename_only() -> None:
    result = QuizImageEntity(filename="abc.jpeg")

    assert result.filename == "abc.jpeg"
    assert result.description is None
