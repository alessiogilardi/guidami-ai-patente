from commons.entities.knowledge import KnowledgeChunk


def _chunk(**kwargs) -> KnowledgeChunk:
    defaults = dict(
        source="cds",
        article_number="1",
        article_title="Finalità ed ambito di applicazione del codice",
        comma_index=1,
        chunk_text="La sicurezza delle persone nella circolazione stradale.",
        is_repealed=False,
        source_url="https://example.com/art-1",
    )
    return KnowledgeChunk(**{**defaults, **kwargs})


def test_knowledge_chunk_defaults_embedding_to_none() -> None:
    chunk = _chunk()
    assert chunk.embedding is None


def test_knowledge_chunk_defaults_context_to_empty_string() -> None:
    chunk = _chunk()
    assert chunk.context == ""


def test_embedded_text_without_context_joins_title_and_text() -> None:
    chunk = _chunk(article_title="Finalità", chunk_text="La sicurezza.", context="")
    assert chunk.embedded_text == "Finalità\nLa sicurezza."


def test_embedded_text_with_context_includes_context_between_title_and_text() -> None:
    chunk = _chunk(
        article_title="Finalità",
        context="Il comma disciplina gli obblighi di sicurezza.",
        chunk_text="La sicurezza.",
    )
    assert chunk.embedded_text == (
        "Finalità\nIl comma disciplina gli obblighi di sicurezza.\nLa sicurezza."
    )


def test_embedded_text_skips_empty_parts() -> None:
    chunk = _chunk(article_title="Finalità", context="", chunk_text="La sicurezza.")
    assert chunk.embedded_text == "Finalità\nLa sicurezza."
