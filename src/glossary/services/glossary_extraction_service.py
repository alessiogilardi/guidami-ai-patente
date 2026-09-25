import logging

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from glossary.agents.glossary_extractor.dto import GlossaryExtractorRequest
from glossary.agents.glossary_extractor.glossary_extractor_agent import GlossaryExtractorAgent
from glossary.configs import GlossaryConfig
from glossary.models import ExtractedEntry, GlossaryBlock
from glossary.utils import capitalize_definition, normalize_term, split_into_chunks

logger = logging.getLogger(__name__)


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
        """Extracts every term/definition pair from `request`'s block text.

        Terms are uppercased and definitions get their first letter capitalized, so
        the same word extracted from a different marker form (numeric vs. alphabetic)
        or in a different chunk converges to the same value. A duplicate normalized
        term within the same comma (e.g. from two separately-extracted chunks) is
        deduplicated, keeping the first occurrence — the same term in a different
        comma is a legitimate distinct entry and is left untouched.
        """
        entries: list[ExtractedEntry] = []
        seen_terms: set[tuple[str, str]] = set()
        for chunk_start, chunk_text in split_into_chunks(
            request.text, self.config.max_block_chars
        ):
            response = await self.agent.run(GlossaryExtractorRequest(block_text=chunk_text))
            for dto in response.entries:
                absolute_offset = chunk_start + chunk_text.index(dto.definition)
                comma_number = request.get_comma_number_at(absolute_offset)
                term = normalize_term(dto.term)
                dedup_key = (comma_number, term)
                if dedup_key in seen_terms:
                    logger.warning(
                        "Duplicate term %r for comma %r skipped after normalization",
                        term,
                        comma_number,
                    )
                else:
                    seen_terms.add(dedup_key)
                    entries.append(
                        ExtractedEntry(
                            term=term,
                            definition=capitalize_definition(dto.definition),
                            comma_number=comma_number,
                        )
                    )
        return entries
