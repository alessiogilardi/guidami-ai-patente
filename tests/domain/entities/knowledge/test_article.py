from domain.entities.knowledge import ArticleEntity


def test_article_entity_has_no_id_field() -> None:
    article = ArticleEntity(
        source="cds",
        number="142",
        title="Titolo",
        url="https://example.com/142",
        is_repealed=False,
    )

    assert "id" not in ArticleEntity.model_fields
    assert article.source == "cds"
    assert article.number == "142"
    assert article.title == "Titolo"
    assert article.url == "https://example.com/142"
    assert article.is_repealed is False
    assert all(field.is_required() for field in ArticleEntity.model_fields.values())
