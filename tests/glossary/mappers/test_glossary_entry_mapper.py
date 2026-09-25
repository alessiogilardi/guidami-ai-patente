from glossary.configs import GlossaryBlockConfig
from glossary.mappers import GlossaryEntryMapper
from glossary.models import ExtractedEntry


def test_it_maps_to_an_entity_with_term_ru_always_none() -> None:
    entry = ExtractedEntry(
        term="carreggiata", definition="Parte della strada...", comma_number="1"
    )
    block = GlossaryBlockConfig(source="cds", file="x.json", article_number="3", comma_number="1")

    entity = GlossaryEntryMapper.from_extracted_to_entity(entry, block, [0.1] * 1536)

    assert entity.source == "cds"
    assert entity.article_number == "3"
    assert entity.comma_number == "1"
    assert entity.term == "carreggiata"
    assert entity.term_ru is None
    assert entity.embedding == [0.1] * 1536
