from pathlib import Path

from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import JsonRepository
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel, ParsedArticleModel
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleCleaner

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


_article_repo = JsonRepository.get_instance(
    ParsedArticleModel, LocalFileSystemClient(FIXTURES_DIR)
)


def _load_cds() -> dict[str, EnrichedArticleModel]:
    articles = _article_repo.load("cds_sample.json")
    cleaned = {article.number: ArticleCleaner().execute(article) for article in articles}
    return {
        number: EnrichedArticleModel(
            number=article.number,
            title=article.title,
            text=article.text,
            paragraphs=article.paragraphs,
            url=article.url,
            scraped_at=article.scraped_at,
            repealed=article.repealed,
        )
        for number, article in cleaned.items()
    }


def _load_cap() -> dict[str, EnrichedArticleModel]:
    articles = _article_repo.load("cap_sample.json")
    cleaned = {article.number: ArticleCleaner().execute(article) for article in articles}
    return {
        number: EnrichedArticleModel(
            number=article.number,
            title=article.title,
            text=article.text,
            paragraphs=article.paragraphs,
            url=article.url,
            scraped_at=article.scraped_at,
            repealed=article.repealed,
        )
        for number, article in cleaned.items()
    }


def test_normal_article_chunks_text_and_paragraphs() -> None:
    article = _load_cds()["1"]

    chunks = ArticleChunker("cds").execute(article)

    assert [chunk.comma_index for chunk in chunks] == [0, 1, 2, 3, 4]
    assert all(chunk.article_number == "1" for chunk in chunks)
    assert all(chunk.source == "cds" for chunk in chunks)
    assert all("((" not in chunk.chunk_text and "))" not in chunk.chunk_text for chunk in chunks)
    assert chunks[0].chunk_text.startswith("1. La sicurezza")
    assert all(chunk.is_repealed is False for chunk in chunks)


def test_empty_text_article_starts_chunking_from_paragraphs() -> None:
    article = _load_cap()["118"]

    chunks = ArticleChunker("cap").execute(article)

    assert [chunk.comma_index for chunk in chunks] == [1, 2, 3, 4]


def test_abrogato_comma_marks_only_that_chunk_as_repealed() -> None:
    article = _load_cds()["231"]

    chunks = ArticleChunker("cds").execute(article)

    by_comma = {chunk.comma_index: chunk for chunk in chunks}
    assert by_comma[1].is_repealed is True
    assert by_comma[2].is_repealed is True
    assert by_comma[3].is_repealed is False


def test_fully_repealed_article_marks_all_chunks_as_repealed() -> None:
    article = _load_cds()["2"]

    chunks = ArticleChunker("cds").execute(article)

    assert len(chunks) == 10
    assert all(chunk.is_repealed is True for chunk in chunks)


def test_non_numeric_article_number_is_kept_as_string() -> None:
    article = _load_cds()["94-bis"]

    chunks = ArticleChunker("cds").execute(article)

    assert all(chunk.article_number == "94-bis" for chunk in chunks)


def test_article_with_empty_cleaned_text_skips_comma_zero() -> None:
    article = _load_cds()["116-bis"]

    chunks = ArticleChunker("cds").execute(article)

    assert [chunk.comma_index for chunk in chunks] == [1]


def test_chunk_context_populated_from_enriched_article_contexts() -> None:
    article = _load_cds()["1"]
    article = article.model_copy(update={"contexts": {0: "Contesto del comma 0."}})

    chunks = ArticleChunker("cds").execute(article)

    by_comma = {chunk.comma_index: chunk for chunk in chunks}
    assert by_comma[0].context == "Contesto del comma 0."
    assert by_comma[1].context == ""


def test_chunk_context_defaults_to_empty_when_not_in_enriched() -> None:
    article = _load_cds()["1"]

    chunks = ArticleChunker("cds").execute(article)

    assert all(chunk.context == "" for chunk in chunks)
