from domain.entities.knowledge import ArticleComma


def test_article_comma_entity_carries_article_id() -> None:
    comma = ArticleComma(
        article_id=1,
        comma_number="1",
        position=0,
        text="Testo del comma",
        is_repealed=False,
        embedding=None,
    )

    assert comma.article_id == 1
    assert "id" not in ArticleComma.model_fields
