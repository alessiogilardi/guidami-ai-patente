from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from glossary.agents.glossary_extractor.dto import GlossaryExtractorRequest
from glossary.agents.glossary_extractor.glossary_extractor_agent import GlossaryExtractorAgent
from glossary.configs import GlossaryConfig
from glossary.models import ExtractedEntry, GlossaryBlock

from ._chunking import split_into_chunks


@service
class GlossaryExtractionService(AsyncUseCase[GlossaryBlock, list[ExtractedEntry]]):
    """Runs the extractor agent over one block's text, chunked as needed (FR-3).

    A block's chunks are extracted independently but all accumulated here before
    returning — the caller (`GlossaryBuildService`) only ever sees a fully-extracted
    block or a raised exception, never a partial one (FR-3).
    """

    config: Autowired[GlossaryConfig]
    agent: Autowired[GlossaryExtractorAgent]

    async def execute(self, request: GlossaryBlock) -> list[ExtractedEntry]:
        entries: list[ExtractedEntry] = []
        for chunk_start, chunk_text in split_into_chunks(
            request.text, self.config.max_block_chars
        ):
            response = await self.agent.run(GlossaryExtractorRequest(block_text=chunk_text))
            for dto in response.entries:
                absolute_offset = chunk_start + chunk_text.index(dto.definition)
                entries.append(
                    ExtractedEntry(
                        term=dto.term,
                        definition=dto.definition,
                        comma_number=request.comma_number_at(absolute_offset),
                    )
                )
        return entries
