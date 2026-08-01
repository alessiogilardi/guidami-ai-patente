from domain.entities.knowledge import ArticleCommaEntity


def test_article_comma_entity_carries_article_id() -> None:
    comma = ArticleCommaEntity(
        article_id=1,
        comma_number="1",
        position=0,
        text="Testo del comma",
        is_repealed=False,
        embedding=None,
    )

    assert comma.article_id == 1
    assert "id" not in ArticleCommaEntity.model_fields
