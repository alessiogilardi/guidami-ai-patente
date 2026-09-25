import types

from glossary.agents.glossary_extractor.dto import ExtractedEntryDto, GlossaryExtractorResponse
from glossary.models import CommaSpan, GlossaryBlock
from glossary.services.glossary_extraction_service import GlossaryExtractionService


class _FakeExtractorAgent:
    def __init__(self, responses: list[GlossaryExtractorResponse]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    async def run(self, request):  # noqa: ANN001, ANN201
        self.calls.append(request.block_text)
        return self._responses[len(self.calls) - 1]


def _service(agent: _FakeExtractorAgent, max_block_chars: int = 1000) -> GlossaryExtractionService:
    service = GlossaryExtractionService.__new__(GlossaryExtractionService)
    service.agent = agent  # type: ignore[attr-defined]
    service.config = types.SimpleNamespace(max_block_chars=max_block_chars)  # type: ignore[attr-defined]
    return service


async def test_a_block_under_the_limit_is_extracted_in_one_call() -> None:
    block = GlossaryBlock(
        source="cds",
        article_number="9",
        text="1) ALFA: uno. 2) BETA: due.",
        comma_spans=(CommaSpan(comma_number="1", start=0, end=27),),
    )
    agent = _FakeExtractorAgent(
        [
            GlossaryExtractorResponse(
                entries=[
                    ExtractedEntryDto(term="ALFA", definition="uno"),
                    ExtractedEntryDto(term="BETA", definition="due"),
                ]
            )
        ]
    )
    entries = await _service(agent)(block)
    assert len(agent.calls) == 1
    assert [e.term for e in entries] == ["ALFA", "BETA"]
    assert all(e.comma_number == "1" for e in entries)


async def test_a_block_over_the_limit_is_chunked_and_results_concatenated() -> None:
    text = "1) ALFA: uno due tre. 2) BETA: quattro cinque sei. 3) GAMMA: sette otto nove."
    block = GlossaryBlock(
        source="cds",
        article_number="9",
        text=text,
        comma_spans=(CommaSpan(comma_number="1", start=0, end=len(text)),),
    )
    agent = _FakeExtractorAgent(
        [
            GlossaryExtractorResponse(
                entries=[ExtractedEntryDto(term="ALFA", definition="uno due tre")]
            ),
            GlossaryExtractorResponse(
                entries=[
                    ExtractedEntryDto(term="BETA", definition="quattro cinque sei"),
                    ExtractedEntryDto(term="GAMMA", definition="sette otto nove"),
                ]
            ),
        ]
    )
    entries = await _service(agent, max_block_chars=40)(block)
    assert len(agent.calls) == 2
    assert [e.term for e in entries] == ["ALFA", "BETA", "GAMMA"]


async def test_each_entry_is_attributed_to_the_comma_it_came_from() -> None:
    text = "Prima\n\nSeconda"
    block = GlossaryBlock(
        source="cds",
        article_number="9",
        text=text,
        comma_spans=(
            CommaSpan(comma_number="1", start=0, end=5),
            CommaSpan(comma_number="2", start=7, end=14),
        ),
    )
    agent = _FakeExtractorAgent(
        [
            GlossaryExtractorResponse(
                entries=[
                    ExtractedEntryDto(term="A", definition="Prima"),
                    ExtractedEntryDto(term="B", definition="Seconda"),
                ]
            )
        ]
    )
    entries = await _service(agent)(block)
    assert {e.term: e.comma_number for e in entries} == {"A": "1", "B": "2"}
