"""Test consolidato per JsonRepository.get_instance() su tutti i modelli supportati.

Sostituisce i 4 test per-sottoclasse (ArticleRepository, EnrichedArticleRepository,
QuizBankRepository, EnrichedQuizBankRepository) con un unico test parametrizzato
che passa per ``JsonRepository.get_instance(Model)``.

NOTE (SP09 plans/ingest--orchestrator/09-quiz-flatten-at-preparation.md): i modelli
quiz `QuizBankModel`/`QuizBankItemModel` sono rinominati in `ParsedQuizModel`/
`ParsedQuizItemModel` (nested, layer "parsed"); `EnrichedQuizModel` è ora flat
(niente più `EnrichedQuizItemModel`/`sub_questions`).
"""

import json
from pathlib import Path

import pytest

from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle
from guidami_ai_patente_ingestor.models.quiz import (
    EnrichedQuizModel,
    ParsedQuizItemModel,
    ParsedQuizModel,
)
from guidami_ai_patente_ingestor.repositories import JsonRepository

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


# ---------------------------------------------------------------------------
# Factory helpers (un modello semplice per tipo)
# ---------------------------------------------------------------------------


def _article(number: str = "1") -> Article:
    return Article(
        number=number,
        title=f"Articolo {number}",
        text=f"Testo {number}.",
        paragraphs=[f"Comma 1 art {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
    )


def _enriched_article(number: str = "1") -> EnrichedArticle:
    return EnrichedArticle(
        number=number,
        title=f"Articolo {number}",
        text=f"Testo {number}.",
        paragraphs=[f"Comma 1 art {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
        contexts={0: "Contesto.", 1: "Altro contesto."},
    )


def _parsed_quiz(question_id: int = 100) -> ParsedQuizModel:
    return ParsedQuizModel(
        question_id=question_id,
        topic="Segnaletica",
        sub_questions=[
            ParsedQuizItemModel(
                number="1",
                text="Domanda?",
                correct_answer=True,
                image="img.jpeg",
            ),
        ],
    )


def _enriched_quiz(
    question_id: int = 100,
    image_description: str | None = "Segnale di stop.",
) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=question_id,
        topic="Segnaletica",
        number="1",
        text="Domanda?",
        correct_answer=True,
        image="img.jpeg",
        image_description=image_description,
    )


# ---------------------------------------------------------------------------
# Round-trip parametrizzato sui 4 modelli
# ---------------------------------------------------------------------------

ROUND_TRIP_CASES = [
    pytest.param(_article, Article, id="Article"),
    pytest.param(_enriched_article, EnrichedArticle, id="EnrichedArticle"),
    pytest.param(_parsed_quiz, ParsedQuizModel, id="ParsedQuizModel"),
    pytest.param(_enriched_quiz, EnrichedQuizModel, id="EnrichedQuizModel"),
]


class TestRoundTrip:
    """Round-trip write → load per ogni modello tramite JsonRepository.get_instance."""

    @pytest.mark.parametrize("factory,model_cls", ROUND_TRIP_CASES)
    def test_write_then_load_round_trips(self, factory, model_cls, tmp_path: Path) -> None:
        path = tmp_path / "layer" / "source.json"
        items = [factory()]
        repo = JsonRepository.get_instance(model_cls)

        repo.write(items, path)
        loaded = repo.load(path)

        assert len(loaded) == 1
        assert loaded == items

    @pytest.mark.parametrize("factory,model_cls", ROUND_TRIP_CASES)
    def test_write_creates_parent_directories(self, factory, model_cls, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "data.json"
        repo = JsonRepository.get_instance(model_cls)

        repo.write([factory()], path)
        assert path.exists()

    @pytest.mark.parametrize("factory,model_cls", ROUND_TRIP_CASES)
    def test_load_empty_list_returns_empty_list(self, factory, model_cls, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text("[]", encoding="utf-8")
        repo = JsonRepository.get_instance(model_cls)

        assert repo.load(path) == []


# ---------------------------------------------------------------------------
# UTF-8 preservation (accentate italiane)
# ---------------------------------------------------------------------------


def test_write_preserves_utf8_characters(tmp_path: Path) -> None:
    path = tmp_path / "enriched.json"
    articles = [
        EnrichedArticle(
            number="1",
            title="Articolo 1",
            text="Testo.",
            paragraphs=["Comma 1."],
            url="https://example.com/art-1",
            scraped_at="2025-01-01T00:00:00",
            repealed=False,
            contexts={0: "È obbligatorio indossare le cinture."},
        )
    ]
    repo = JsonRepository.get_instance(EnrichedArticle)
    repo.write(articles, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw[0]["contexts"]["0"] == "È obbligatorio indossare le cinture."


# ---------------------------------------------------------------------------
# Fixture-based field mapping: Article ← cds_sample.json / cap_sample.json
# ---------------------------------------------------------------------------


def test_article_load_from_cds_sample() -> None:
    repo = JsonRepository.get_instance(Article)
    articles = repo.load(FIXTURES_DIR / "cds_sample.json")

    article_1 = next(a for a in articles if a.number == "1")
    assert article_1.title == "Principi generali"
    assert article_1.repealed is False
    assert article_1.text.startswith("((1. La sicurezza")
    assert len(article_1.paragraphs) == 4
    assert article_1.url.startswith("https://www.normattiva.it/")


def test_article_load_from_cap_sample_repealed_and_empty_text() -> None:
    repo = JsonRepository.get_instance(Article)
    articles = repo.load(FIXTURES_DIR / "cap_sample.json")

    article_118 = articles[0]
    assert article_118.number == "118"
    assert article_118.text == ""
    assert article_118.repealed is True
    assert len(article_118.paragraphs) == 4


# ---------------------------------------------------------------------------
# Fixture-based field mapping: ParsedQuizModel ← quiz_bank_sample.json
# ---------------------------------------------------------------------------


def test_parsed_quiz_load_from_sample() -> None:
    repo = JsonRepository.get_instance(ParsedQuizModel)
    main_questions = repo.load(FIXTURES_DIR / "quiz_bank_sample.json")

    assert len(main_questions) == 2

    first = main_questions[0]
    assert first.question_id == 100
    assert first.topic == "Segnaletica"
    assert [sub.number for sub in first.sub_questions] == ["1001", "1002", "1003"]
    assert first.sub_questions[0].image == "data/processed/quiz-patente-ab/images/abc123.jpeg"
    assert first.sub_questions[2].image is None
    assert first.sub_questions[1].correct_answer is False


# ---------------------------------------------------------------------------
# Round-trip None for EnrichedQuizModel.image_description
# ---------------------------------------------------------------------------


def test_enriched_quiz_round_trip_none_image_description(tmp_path: Path) -> None:
    path = tmp_path / "quiz.json"
    questions = [
        EnrichedQuizModel(
            question_id=1,
            topic="Segnaletica",
            number="1",
            text="Domanda?",
            correct_answer=True,
            image="img.jpeg",
            image_description=None,
        )
    ]
    repo = JsonRepository.get_instance(EnrichedQuizModel)
    repo.write(questions, path)
    loaded = repo.load(path)

    assert loaded[0].image_description is None
