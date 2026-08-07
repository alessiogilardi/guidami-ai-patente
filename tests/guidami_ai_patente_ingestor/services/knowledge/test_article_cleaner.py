from guidami_ai_patente_ingestor.models.knowledge import ParsedArticleModel, ParsedComma
from guidami_ai_patente_ingestor.services.knowledge import ArticleCleanerService


def _article(**kwargs) -> ParsedArticleModel:
    defaults = dict(
        number="1",
        title="Titolo",
        commas=[ParsedComma(number="1", text="Testo del comma.")],
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
    )
    return ParsedArticleModel(**{**defaults, **kwargs})


def test_title_wrapped_in_parentheses_is_unwrapped() -> None:
    article = _article(
        title=(
            "(Formalità necessarie per la circolazione degli autoveicoli, motoveicoli e "
            "rimorchi immatricolati in uno Stato estero e condotti da residenti in Italia)."
        )
    )

    cleaned = ArticleCleanerService().execute(article)

    assert cleaned.title == (
        "Formalità necessarie per la circolazione degli autoveicoli, motoveicoli e rimorchi "
        "immatricolati in uno Stato estero e condotti da residenti in Italia"
    )


def test_title_without_wrapping_parentheses_is_left_unchanged() -> None:
    article = _article(title="Principi generali")

    cleaned = ArticleCleanerService().execute(article)

    assert cleaned.title == "Principi generali"


def test_title_with_missing_closing_paren_keeps_only_orphan_open_paren_stripped() -> None:
    article = _article(title=" (Opposizione all'ordinanza-ingiunzione")

    cleaned = ArticleCleanerService().execute(article)

    assert cleaned.title == "Opposizione all'ordinanza-ingiunzione"


def test_article_cleaner_strips_residual_markers_from_comma_text() -> None:
    article = ParsedArticleModel(
        number="1",
        title="Titolo",
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
        commas=[ParsedComma(number="1", text="testo ((con marcatori)) residuo")],
    )

    cleaned = ArticleCleanerService().execute(article)

    assert len(cleaned.commas) == 1
    assert cleaned.commas[0].text == "testo con marcatori residuo"


def test_article_cleaner_strips_marker_at_the_start_of_a_comma() -> None:
    article = _article(
        commas=[
            ParsedComma(
                number="4-bis",
                text="((L'utilizzo di un veicolo destinato a noleggio con conducente))",
            )
        ]
    )

    cleaned = ArticleCleanerService().execute(article)

    assert cleaned.commas[0].text == "L'utilizzo di un veicolo destinato a noleggio con conducente"


def test_article_cleaner_strips_multiple_marker_pairs_from_the_same_comma() -> None:
    article = _article(
        commas=[
            ParsedComma(
                number="2",
                text="Sanzione ((da € 543 a € 2.170)) prevista anche per il proprietario ((163))",
            )
        ]
    )

    cleaned = ArticleCleanerService().execute(article)

    assert cleaned.commas[0].text == (
        "Sanzione da € 543 a € 2.170 prevista anche per il proprietario 163"
    )


def test_article_cleaner_comma_with_no_markers_is_left_unchanged() -> None:
    article = _article(
        commas=[ParsedComma(number="1", text="Testo del comma senza marcatori residui.")]
    )

    cleaned = ArticleCleanerService().execute(article)

    assert cleaned.commas[0].text == "Testo del comma senza marcatori residui."


def test_article_cleaner_unbalanced_markup_empties_only_that_comma_text() -> None:
    article = _article(
        commas=[
            ParsedComma(number="1", text="Lo scambio di informazioni con gli altri Stati. (("),
            ParsedComma(number="2", text="Testo regolare del secondo comma."),
        ]
    )

    cleaned = ArticleCleanerService().execute(article)

    assert cleaned.commas[0].text == ""
    assert cleaned.commas[1].text == "Testo regolare del secondo comma."


def test_article_cleaner_never_drops_a_comma() -> None:
    article = ParsedArticleModel(
        number="1",
        title="Titolo",
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
        commas=[
            ParsedComma(number="1", text="Testo primo comma."),
            ParsedComma(number="2", text="Testo secondo comma."),
            ParsedComma(number="3", text="Testo terzo comma."),
        ],
    )

    cleaned = ArticleCleanerService().execute(article)

    assert [comma.number for comma in cleaned.commas] == ["1", "2", "3"]


def test_article_cleaner_preserves_comma_numbers_and_order() -> None:
    article = _article(
        commas=[
            ParsedComma(number="1", text="Primo."),
            ParsedComma(number="1-bis", text="Uno bis."),
            ParsedComma(number="2", text="Secondo."),
        ]
    )

    cleaned = ArticleCleanerService().execute(article)

    assert [comma.number for comma in cleaned.commas] == ["1", "1-bis", "2"]


def test_article_cleaner_empty_comma_text_is_left_unchanged() -> None:
    article = _article(commas=[ParsedComma(number="1", text="")])

    cleaned = ArticleCleanerService().execute(article)

    assert cleaned.commas[0].text == ""
