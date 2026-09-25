# tests/glossary/test_extraction_spike.py
"""Real-LLM spike validating extraction quality (AD-10), not a plan-blocking gate.

Runs the smallest block first (art. 157), then the two chunked blocks (CdS art. 3,
CAP art. 1) that motivated AD-10's mechanical chunking. Requires OPENROUTER_API_KEY
to be a real key — skipped otherwise.
"""

import os

import pytest
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.ai.observability import NullLlmCallTracker
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository
from glossary.agents.glossary_extractor.dto import GlossaryExtractorRequest
from glossary.agents.glossary_extractor.glossary_extractor_agent import GlossaryExtractorAgent
from glossary.configs import GlossaryBlockConfig
from glossary.repositories import GlossaryBlockReadRepository
from glossary.services._chunking import split_into_chunks

pytestmark = pytest.mark.integration

_REAL_KEY = os.environ.get("OPENROUTER_API_KEY", "")


@pytest.mark.skipif(
    _REAL_KEY.startswith("test-key") or not _REAL_KEY, reason="requires a real OPENROUTER_API_KEY"
)
@pytest.mark.parametrize(
    ("article_number", "comma_number", "min_entries"),
    [("157", "1", 3), ("3", "1", 40), ("1", "1", 30)],
)
async def test_extraction_produces_a_plausible_entry_count(
    article_number: str, comma_number: str, min_entries: int
) -> None:
    source = "cap" if article_number == "1" and min_entries == 30 else "cds"
    file_name = (
        "cap/codice_assicurazioni_private.json"
        if source == "cap"
        else "cds/codice_della_strada.json"
    )
    block_config = GlossaryBlockConfig(
        source=source, file=file_name, article_number=article_number, comma_number=comma_number
    )
    reader = GlossaryBlockReadRepository(parsed_dir="data/parsed")
    block = reader.read(block_config)

    agent_config_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient("configs/agents")
    )
    agent_config = agent_config_repository.load_one("glossary_extractor.yaml")
    agent = GlossaryExtractorAgent(
        agent_config, OpenRouterProvider(api_key=_REAL_KEY), NullLlmCallTracker()
    )

    entries = []
    for _, chunk_text in split_into_chunks(block.text, max_chars=6000):
        response = await agent.run(GlossaryExtractorRequest(block_text=chunk_text))
        entries.extend(response.entries)

    assert len(entries) >= min_entries, [e.term for e in entries]
