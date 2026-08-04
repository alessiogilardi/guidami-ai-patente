import json
import random
from pathlib import Path

from test_data_sampler.sampler import sample_knowledge_source, sample_quiz


def _article(number: str) -> dict[str, object]:
    return {
        "number": number,
        "title": f"Titolo {number}",
        "commas": [{"number": "1", "text": f"Testo {number}"}],
    }


def _quiz_question(question_id: str, image: str | None) -> dict[str, object]:
    return {
        "question_id": question_id,
        "topic": "Segnali",
        "sub_questions": [
            {
                "number": f"{question_id}0",
                "text": f"Domanda {question_id}",
                "correct_answer": True,
                "image": image,
            }
        ],
    }


def test_sample_knowledge_source_writes_a_random_subset(tmp_path: Path) -> None:
    articles = [_article(str(number)) for number in range(1, 11)]
    source_path = tmp_path / "source.json"
    dest_path = tmp_path / "dest.json"
    source_path.write_text(json.dumps(articles, ensure_ascii=False), encoding="utf-8")

    sample_knowledge_source(source_path, dest_path, count=3, rng=random.Random(42))

    written = json.loads(dest_path.read_text(encoding="utf-8"))
    assert len(written) == 3
    expected_by_number = {article["number"]: article for article in articles}
    for article in written:
        assert article == expected_by_number[article["number"]]


def test_sample_knowledge_source_caps_at_the_available_count(tmp_path: Path) -> None:
    articles = [_article(str(number)) for number in range(1, 4)]
    source_path = tmp_path / "source.json"
    dest_path = tmp_path / "dest.json"
    source_path.write_text(json.dumps(articles, ensure_ascii=False), encoding="utf-8")

    sample_knowledge_source(source_path, dest_path, count=100, rng=random.Random(1))

    written = json.loads(dest_path.read_text(encoding="utf-8"))
    assert len(written) == 3


def test_sample_knowledge_source_creates_missing_dest_dirs(tmp_path: Path) -> None:
    source_path = tmp_path / "source.json"
    dest_path = tmp_path / "nested" / "dir" / "dest.json"
    source_path.write_text(json.dumps([_article("1")], ensure_ascii=False), encoding="utf-8")

    sample_knowledge_source(source_path, dest_path, count=1, rng=random.Random(1))

    assert dest_path.exists()


def test_sample_quiz_copies_only_the_sampled_questions_images(tmp_path: Path) -> None:
    questions = [
        _quiz_question("1", "a.jpeg"),
        _quiz_question("2", "b.jpeg"),
        _quiz_question("3", None),
    ]
    source_path = tmp_path / "quiz.json"
    dest_path = tmp_path / "test-data" / "quiz.json"
    images_source_dir = tmp_path / "images"
    images_source_dir.mkdir()
    (images_source_dir / "a.jpeg").write_bytes(b"fake-a")
    (images_source_dir / "b.jpeg").write_bytes(b"fake-b")
    images_dest_dir = tmp_path / "test-data" / "images"
    source_path.write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")

    sample_quiz(
        source_path, dest_path, images_source_dir, images_dest_dir, count=2, rng=random.Random(7)
    )

    written = json.loads(dest_path.read_text(encoding="utf-8"))
    assert len(written) == 2
    copied_images = {path.name for path in images_dest_dir.iterdir()}
    referenced_images = {
        sub_question["image"]
        for question in written
        for sub_question in question["sub_questions"]
        if sub_question.get("image")
    }
    assert copied_images == referenced_images


def test_sample_quiz_handles_no_images_referenced(tmp_path: Path) -> None:
    questions = [_quiz_question("1", None), _quiz_question("2", None)]
    source_path = tmp_path / "quiz.json"
    dest_path = tmp_path / "dest.json"
    images_source_dir = tmp_path / "images"
    images_source_dir.mkdir()
    images_dest_dir = tmp_path / "images-dest"
    source_path.write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")

    sample_quiz(
        source_path, dest_path, images_source_dir, images_dest_dir, count=2, rng=random.Random(3)
    )

    assert list(images_dest_dir.iterdir()) == []
