from domain.entities.glossary import GlossaryEntryEntity


def test_it_holds_exactly_the_insertable_columns() -> None:
    entity = GlossaryEntryEntity(
        source="cds",
        article_number="3",
        comma_number="1",
        term="carreggiata",
        definition="Parte della strada destinata allo scorrimento dei veicoli.",
        term_ru=None,
        embedding=[0.1] * 1536,
    )
    assert entity.term_ru is None
    assert len(entity.embedding) == 1536
