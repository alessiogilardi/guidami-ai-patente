from pathlib import Path

from parsers.questions_pdf import (
    Question,
    SubQuestion,
    _get_headers_with_y,
    _prune_orphans,
    _referenced_images,
)


class _FakePage:
    """Mimics pdfplumber's `Page`.

    Exposes only `extract_words()`, the sole method used by `_get_headers_with_y`.
    """

    def __init__(self, lines: list[tuple[float, str]]) -> None:
        self._words = [
            {"text": token, "top": top, "x0": float(x0)}
            for top, text in lines
            for x0, token in enumerate(text.split(" "))
        ]

    def extract_words(self) -> list[dict]:
        return self._words


def test_single_line_topic_is_captured_unchanged() -> None:
    page = _FakePage(
        [
            (100.0, "Quesito n° 4328 - Segnali di indicazione"),
            (120.0, "Numero Testo domanda Risposta Corretta Immagine"),
        ]
    )

    headers, leading_continuation, topic_open = _get_headers_with_y(page)  # type: ignore[arg-type]

    assert headers == [(100.0, "4328", "Segnali di indicazione")]
    assert leading_continuation == ""
    assert topic_open is False


def test_two_line_topic_wrap_ends_at_table_header_row() -> None:
    page = _FakePage(
        [
            (
                201.0,
                "Quesito n° 4409 - Norme sulla circol. dei veicoli; comp. in presenza di",
            ),
            (217.0, "funerali, cortei, convogli militari; norme di prec."),
            (254.0, "Numero Testo domanda Risposta Corretta Immagine"),
        ]
    )

    headers, leading_continuation, topic_open = _get_headers_with_y(page)  # type: ignore[arg-type]

    assert headers == [
        (
            201.0,
            "4409",
            "Norme sulla circol. dei veicoli; comp. in presenza di "
            "funerali, cortei, convogli militari; norme di prec.",
        )
    ]
    assert leading_continuation == ""
    assert topic_open is False


def test_topic_wrap_does_not_swallow_next_quesito_header() -> None:
    page = _FakePage(
        [
            (100.0, "Quesito n° 4001 - Definizioni stradali e di traffico -"),
            (116.0, "convivenza civile ed uso responsabile della strada"),
            (132.0, "ciclisti"),
            (150.0, "Quesito n° 4002 - Segnaletica orizzontale"),
            (166.0, "Numero Testo domanda Risposta Corretta Immagine"),
        ]
    )

    headers, leading_continuation, topic_open = _get_headers_with_y(page)  # type: ignore[arg-type]

    assert headers == [
        (
            100.0,
            "4001",
            "Definizioni stradali e di traffico - convivenza civile ed uso responsabile "
            "della strada ciclisti",
        ),
        (150.0, "4002", "Segnaletica orizzontale"),
    ]
    assert leading_continuation == ""
    assert topic_open is False


def test_topic_wrap_ends_at_data_row_without_header_row() -> None:
    page = _FakePage(
        [
            (100.0, "Quesito n° 4328 - Segnali di indicazione stradale"),
            (116.0, "e complementare"),
            (140.0, "21810 Testo della domanda VERO"),
        ]
    )

    headers, leading_continuation, topic_open = _get_headers_with_y(page)  # type: ignore[arg-type]

    assert headers == [(100.0, "4328", "Segnali di indicazione stradale e complementare")]
    assert leading_continuation == ""
    assert topic_open is False


def test_topic_still_open_when_page_ends_mid_wrap() -> None:
    """Reproduces question 4422.

    The header is near the bottom of the page and its topic keeps wrapping with no
    boundary line before the page runs out.
    """
    page = _FakePage(
        [
            (793.0, "Quesito n° 4422 - Norme sulla circol. dei veicoli; comp. in presenza di"),
            (809.0, "funerali, cortei, convogli militari; rischi legati a manovra e a"),
        ]
    )

    headers, leading_continuation, topic_open = _get_headers_with_y(page)  # type: ignore[arg-type]

    assert headers == [
        (
            793.0,
            "4422",
            "Norme sulla circol. dei veicoli; comp. in presenza di "
            "funerali, cortei, convogli militari; rischi legati a manovra e a",
        )
    ]
    assert leading_continuation == ""
    assert topic_open is True


def test_resume_topic_consumes_leading_continuation_until_boundary() -> None:
    """The next page after test_topic_still_open_when_page_ends_mid_wrap.

    No new quesito header, just the tail of 4422's topic followed by the table.
    """
    page = _FakePage(
        [
            (29.0, "guida dei diversi tipi di veicolo e relativo campo visivo del cond."),
            (50.0, "Numero Testo domanda Risposta Corretta Immagine"),
            (72.0, "22789 Testo della domanda VERO"),
        ]
    )

    headers, leading_continuation, topic_open = _get_headers_with_y(
        page,  # type: ignore[arg-type]
        resume_topic=True,
    )

    assert headers == []
    assert (
        leading_continuation
        == "guida dei diversi tipi di veicolo e relativo campo visivo del cond."
    )
    assert topic_open is False


def test_resume_topic_still_open_when_whole_page_is_continuation() -> None:
    page = _FakePage(
        [
            (29.0, "guida dei diversi tipi di veicolo e relativo campo visivo del cond."),
            (45.0, "e altre considerazioni finali sul comportamento di guida"),
        ]
    )

    headers, leading_continuation, topic_open = _get_headers_with_y(
        page,  # type: ignore[arg-type]
        resume_topic=True,
    )

    assert headers == []
    assert leading_continuation == (
        "guida dei diversi tipi di veicolo e relativo campo visivo del cond. "
        "e altre considerazioni finali sul comportamento di guida"
    )
    assert topic_open is True


def test_resume_topic_then_new_header_on_same_page() -> None:
    page = _FakePage(
        [
            (29.0, "guida dei diversi tipi di veicolo e relativo campo visivo del cond."),
            (50.0, "Numero Testo domanda Risposta Corretta Immagine"),
            (72.0, "22789 Testo della domanda VERO"),
            (100.0, "Quesito n° 4423 - Segnaletica orizzontale"),
            (116.0, "Numero Testo domanda Risposta Corretta Immagine"),
        ]
    )

    headers, leading_continuation, topic_open = _get_headers_with_y(
        page,  # type: ignore[arg-type]
        resume_topic=True,
    )

    assert headers == [(100.0, "4423", "Segnaletica orizzontale")]
    assert (
        leading_continuation
        == "guida dei diversi tipi di veicolo e relativo campo visivo del cond."
    )
    assert topic_open is False


def _sub_question(number: str, image: str | None) -> SubQuestion:
    return SubQuestion(number=number, text="Testo", correct_answer=True, image=image)


def _question(question_id: str, images: list[str | None]) -> Question:
    return Question(
        question_id=question_id,
        topic="Segnali",
        sub_questions=[
            _sub_question(f"{question_id}{i}", image) for i, image in enumerate(images)
        ],
    )


def test_referenced_images_collects_every_non_null_image_filename() -> None:
    questions = [
        _question("1", ["a.jpeg", None]),
        _question("2", ["b.jpeg", "a.jpeg"]),
    ]

    assert _referenced_images(questions) == {"a.jpeg", "b.jpeg"}


def test_referenced_images_empty_when_no_question_has_an_image() -> None:
    questions = [_question("1", [None, None])]

    assert _referenced_images(questions) == set()


def test_prune_orphans_removes_only_unreferenced_files(tmp_path: Path) -> None:
    (tmp_path / "a.jpeg").write_bytes(b"referenced")
    (tmp_path / "b.jpeg").write_bytes(b"orphan")

    pruned = _prune_orphans(tmp_path, referenced={"a.jpeg"})

    assert pruned == 1
    assert {p.name for p in tmp_path.iterdir()} == {"a.jpeg"}


def test_prune_orphans_returns_zero_when_nothing_is_orphaned(tmp_path: Path) -> None:
    (tmp_path / "a.jpeg").write_bytes(b"referenced")

    pruned = _prune_orphans(tmp_path, referenced={"a.jpeg"})

    assert pruned == 0
    assert {p.name for p in tmp_path.iterdir()} == {"a.jpeg"}
