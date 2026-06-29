from pathlib import Path

from guidami_ai_patente_ingestor.models.knowledge import ParsedArticleModel
from guidami_ai_patente_ingestor.repositories import JsonRepository
from guidami_ai_patente_ingestor.services.knowledge import ArticleCleaner

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


def _load_cds() -> dict[str, object]:
    articles = JsonRepository.get_instance(ParsedArticleModel).load(
        FIXTURES_DIR / "cds_sample.json"
    )
    return {article.number: ArticleCleaner().clean(article) for article in articles}


def test_inline_markup_is_removed_from_text_and_paragraphs() -> None:
    article = _load_cds()["1"]

    assert article.text.startswith("1. La sicurezza")
    assert "((" not in article.text and "))" not in article.text
    assert all("((" not in p and "))" not in p for p in article.paragraphs)


def test_paragraph_ordinals_are_stripped() -> None:
    article = _load_cds()["1"]

    assert article.paragraphs[0].startswith("La circolazione dei pedoni")


def test_inline_markup_in_the_middle_of_a_paragraph_is_resolved() -> None:
    article = _load_cds()["94-bis"]

    second_paragraph = article.paragraphs[1]
    assert "da € 543 a € 2.170" in second_paragraph
    assert "163" in second_paragraph
    assert "((" not in second_paragraph and "))" not in second_paragraph


def test_standalone_markers_are_dropped_without_losing_commi() -> None:
    article = _load_cds()["28"]

    assert article.paragraphs == [
        "I concessionari di ferrovie, di tranvie, di filovie hanno l'obbligo di osservare le "
        "condizioni e le prescrizioni imposte dall'ente proprietario per la conservazione "
        "della strada e per la sicurezza della circolazione.",
        "Qualora per comprovate esigenze della viabilità si renda necessario modificare o "
        "spostare gli impianti, l'onere relativo allo spostamento è a carico del gestore "
        "del pubblico servizio.",
    ]


def test_title_wrapped_in_parentheses_is_unwrapped() -> None:
    article = _load_cds()["93-bis"]

    assert article.title == (
        "Formalità necessarie per la circolazione degli autoveicoli, motoveicoli e rimorchi "
        "immatricolati in uno Stato estero e condotti da residenti in Italia"
    )


def test_fully_wrapped_comma_is_unwrapped_and_footnote_reference_is_dropped() -> None:
    article = _load_cds()["93-bis"]

    assert article.paragraphs == [
        "Fuori dei casi di cui al comma 3, gli autoveicoli immatricolati in uno Stato estero "
        "sono ammessi a circolare sul territorio nazionale.",
        "A bordo del veicolo deve essere custodito un documento che attesti il titolo e la "
        "durata della disponibilità.",
    ]


def test_lettered_sub_items_spread_across_elements_are_merged_into_one_comma() -> None:
    article = _load_cds()["85"]

    assert len(article.paragraphs) == 1
    comma = article.paragraphs[0]
    assert comma.startswith("L'utilizzo di un veicolo")
    assert "da euro 178 a euro 672" in comma
    assert "da euro 264 a euro 1.010" in comma
    assert "((" not in comma and "))" not in comma


def test_ordinal_without_trailing_dot_is_stripped() -> None:
    article = _load_cds()["61"]

    assert article.paragraphs[1].startswith("Gli autosnodati e i filosnodati")


def test_markers_wrapping_a_range_of_already_numbered_commi_are_dropped() -> None:
    article = _load_cds()["9-bis"]

    assert len(article.paragraphs) == 2
    assert article.paragraphs[0].startswith("Salvo che il fatto costituisca")
    assert article.paragraphs[1].startswith("Se dallo svolgimento")


def test_unbalanced_text_markup_is_discarded() -> None:
    article = _load_cds()["116-bis"]

    assert article.text == ""
    assert article.paragraphs[0].startswith("Lo scambio di informazioni")


def test_title_with_missing_closing_paren_keeps_only_orphan_open_paren_stripped() -> None:
    article = _load_cds()["205"]

    assert article.title == "Opposizione all'ordinanza-ingiunzione"


def test_duplicated_ordinal_prefix_is_fully_stripped() -> None:
    article = _load_cds()["226"]

    assert article.paragraphs[1].startswith("Nell'archivio nazionale")
