import types

import pytest
from glossary.services.glossary_build_service import GlossaryBuildService
from pydantic_ai.exceptions import UnexpectedModelBehavior

from glossary.configs import GlossaryBlockConfig
from glossary.exceptions import GlossaryBuildError
from glossary.models import ExtractedEntry, GlossaryBlock, GlossaryBuildRequest

_ONE_BLOCK = (
    GlossaryBlockConfig(source="cds", file="x.json", article_number="157", comma_number="1"),
)
_TWO_BLOCKS = (
    *_ONE_BLOCK,
    GlossaryBlockConfig(source="cds", file="x.json", article_number="3", comma_number="1"),
)


class _FakeBlockReader:
    def read(self, block: GlossaryBlockConfig) -> GlossaryBlock:
        return GlossaryBlock(
            source=block.source, article_number=block.article_number, text="x", comma_spans=()
        )


class _FakeEntryReader:
    def __init__(self, already_built: set[str]) -> None:
        self._already_built = already_built

    def has_entries_for(self, block: GlossaryBlockConfig) -> bool:
        return f"{block.article_number}" in self._already_built


class _RaisingEntryReader:
    def has_entries_for(self, block: GlossaryBlockConfig) -> bool:
        raise AssertionError("must not be called when --force is set")


class _FakeExtractionService:
    def __init__(self, entries_by_article: dict[str, list[ExtractedEntry]]) -> None:
        self._entries_by_article = entries_by_article

    async def __call__(self, block: GlossaryBlock) -> list[ExtractedEntry]:
        return self._entries_by_article.get(block.article_number, [])


class _RaisingExtractionService:
    async def __call__(self, block: GlossaryBlock) -> list[ExtractedEntry]:
        raise RuntimeError("boom")


class _NeverCalledExtractionService:
    async def __call__(self, block: GlossaryBlock) -> list[ExtractedEntry]:
        raise AssertionError("must not be called for an already-built block")


class _FakeEmbeddingService:
    def __call__(self, texts):  # noqa: ANN001, ANN201
        return [[0.1] * 1536 for _ in texts]


class _FakeEntryWriter:
    def __init__(self) -> None:
        self.written: list[tuple[str, int]] = []

    def write(self, block: GlossaryBlockConfig, entries) -> None:  # noqa: ANN001
        self.written.append((block.article_number, len(entries)))


def _service(
    blocks, block_reader, entry_reader, extraction_service, entry_writer
) -> GlossaryBuildService:
    service = GlossaryBuildService.__new__(GlossaryBuildService)
    service.config = types.SimpleNamespace(blocks=blocks)  # type: ignore[attr-defined]
    service.block_reader = block_reader  # type: ignore[attr-defined]
    service.entry_reader = entry_reader  # type: ignore[attr-defined]
    service.extraction_service = extraction_service  # type: ignore[attr-defined]
    service.embedding_service = _FakeEmbeddingService()  # type: ignore[attr-defined]
    service.entry_writer = entry_writer  # type: ignore[attr-defined]
    return service


async def test_an_already_built_block_is_skipped_without_extraction() -> None:
    writer = _FakeEntryWriter()
    service = _service(
        _ONE_BLOCK,
        _FakeBlockReader(),
        _FakeEntryReader({"157"}),
        _NeverCalledExtractionService(),
        writer,
    )

    report = await service(GlossaryBuildRequest(force=False))

    assert report.outcomes[0].skipped is True
    assert writer.written == []


async def test_force_rebuilds_without_checking_already_built() -> None:
    writer = _FakeEntryWriter()
    entries = {"157": [ExtractedEntry(term="arresto", definition="def", comma_number="1")]}
    service = _service(
        _ONE_BLOCK,
        _FakeBlockReader(),
        _RaisingEntryReader(),
        _FakeExtractionService(entries),
        writer,
    )

    report = await service(GlossaryBuildRequest(force=True))

    assert report.outcomes[0].skipped is False
    assert writer.written == [("157", 1)]


async def test_a_failing_block_does_not_stop_its_siblings_and_the_run_raises() -> None:
    writer = _FakeEntryWriter()
    entries = {"3": [ExtractedEntry(term="carreggiata", definition="def", comma_number="1")]}
    service = _service(
        _TWO_BLOCKS,
        _FakeBlockReader(),
        _FakeEntryReader(set()),
        _FakeExtractionService(entries),  # "157" is missing -> empty extraction, "3" succeeds
        writer,
    )
    service.extraction_service = _MixedExtractionService(entries)  # type: ignore[attr-defined]

    with pytest.raises(GlossaryBuildError) as excinfo:
        await service(GlossaryBuildRequest(force=False))

    assert excinfo.value.failed_labels == ("cds/157/1",)
    assert writer.written == [("3", 1)]


class _MixedExtractionService:
    def __init__(self, entries_by_article: dict[str, list[ExtractedEntry]]) -> None:
        self._entries_by_article = entries_by_article

    async def __call__(self, block: GlossaryBlock) -> list[ExtractedEntry]:
        if block.article_number == "157":
            raise UnexpectedModelBehavior("boom")
        return self._entries_by_article.get(block.article_number, [])
