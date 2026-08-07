from guidami_ai_patente_ingestor.models.knowledge import EmbeddableArticleComma
from guidami_ai_patente_ingestor.utils import detect_comma_repeal, is_comma_repealed

# --- is_comma_repealed ---


def test_repealed_when_article_repealed() -> None:
    assert is_comma_repealed(article_repealed=True, comma_text="testo normale") is True


def test_repealed_by_own_formula() -> None:
    text = "COMMA ABROGATO DAL D.LGS. 15 MARZO 2010, N. 66 ."

    assert is_comma_repealed(article_repealed=False, comma_text=text) is True


def test_repealed_by_soppresso_formula() -> None:
    text = "COMMA SOPPRESSO DAL D.LGS. 15 MARZO 2010, N. 66 ."

    assert is_comma_repealed(article_repealed=False, comma_text=text) is True


def test_repealed_by_own_formula_with_leading_markers() -> None:
    text = "((COMMA ABROGATO DAL D.LGS. 21 MAGGIO 2018, N. 68 )) ."

    assert is_comma_repealed(article_repealed=False, comma_text=text) is True


def test_not_repealed_on_periodo_abrogato() -> None:
    text = "PERIODO ABROGATO DAL D.LGS. ..."

    assert is_comma_repealed(article_repealed=False, comma_text=text) is False


def test_not_repealed_on_plain_text() -> None:
    assert is_comma_repealed(article_repealed=False, comma_text="Testo del comma.") is False


def test_repealed_on_empty_text() -> None:
    assert is_comma_repealed(article_repealed=False, comma_text="") is True


def test_repealed_on_whitespace_only_text() -> None:
    assert is_comma_repealed(article_repealed=False, comma_text="   \n  ") is True


# --- detect_comma_repeal ---


def _comma(**kwargs) -> EmbeddableArticleComma:
    defaults = dict(
        source="cds",
        article_number="1",
        article_title="Titolo",
        comma_number="1",
        position=0,
        text="Testo del comma.",
        is_repealed=False,
        embedding=None,
    )
    return EmbeddableArticleComma(**{**defaults, **kwargs})


def test_detect_comma_repeal_marks_repealed_by_own_formula() -> None:
    comma = _comma(is_repealed=False, text="COMMA ABROGATO DAL D.LGS. 15 MARZO 2010, N. 66 .")

    result = detect_comma_repeal(comma)

    assert result.is_repealed is True


def test_detect_comma_repeal_preserves_already_repealed_flag() -> None:
    comma = _comma(is_repealed=True, text="testo normale")

    result = detect_comma_repeal(comma)

    assert result.is_repealed is True


def test_detect_comma_repeal_not_repealed_on_plain_text() -> None:
    comma = _comma(is_repealed=False, text="Testo del comma.")

    result = detect_comma_repeal(comma)

    assert result.is_repealed is False


def test_detect_comma_repeal_marks_repealed_on_empty_text() -> None:
    comma = _comma(is_repealed=False, text="")

    result = detect_comma_repeal(comma)

    assert result.is_repealed is True


def test_detect_comma_repeal_leaves_other_fields_unchanged() -> None:
    comma = _comma(
        source="cap",
        article_number="142",
        article_title="Titolo articolo",
        comma_number="2-bis",
        position=3,
        text="Testo del comma.",
        embedding=[0.1, 0.2],
    )

    result = detect_comma_repeal(comma)

    assert result.source == "cap"
    assert result.article_number == "142"
    assert result.article_title == "Titolo articolo"
    assert result.comma_number == "2-bis"
    assert result.position == 3
    assert result.text == "Testo del comma."
    assert result.embedding == [0.1, 0.2]
