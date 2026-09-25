# tests/glossary/test_extraction_spike.py
"""Real-LLM spike validating extraction quality (AD-10), not a plan-blocking gate.

Runs the smallest block first (art. 157), then the two chunked blocks (CdS art. 3,
CAP art. 1) that motivated AD-10's mechanical chunking.

Gated behind TWO independent conditions, both required, checked at test-body
execution time (never at module import/collection time): a real OPENROUTER_API_KEY
and the explicit opt-in GLOSSARY_SPIKE_LIVE=1. `tests/conftest.py`'s session-scoped
`_open_router_environment` fixture pins OPENROUTER_API_KEY to a dummy value for
every test in the suite, but that fixture runs at test setup, after collection —
so a check evaluated at *module* level (a bare `os.environ.get(...)` assigned to a
module constant) executes before the fixture ever applies and can see whatever the
ambient environment happened to hold at collection time. Reading both env vars
fresh, inside the test body, avoids that entirely: by the time this function
runs, the session fixture has already pinned OPENROUTER_API_KEY to
"test-key-not-a-real-credential" for every other test, and only an operator who
explicitly exports GLOSSARY_SPIKE_LIVE=1 for this one deliberate run bypasses it.
No amount of ambient .env/shell state alone can trigger a real, billed call.
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


def _live_run_requested() -> bool:
    """True only when both a real key AND the explicit opt-in are set right now.

    Deliberately re-read at call time, never cached at module level — see the
    module docstring for why that timing matters.
    """
    real_key = os.environ.get("OPENROUTER_API_KEY", "")
    has_real_key = bool(real_key) and not real_key.startswith("test-key")
    return has_real_key and os.environ.get("GLOSSARY_SPIKE_LIVE") == "1"


@pytest.mark.parametrize(
    ("article_number", "comma_number", "min_entries"),
    [("157", "1", 3), ("3", "1", 40), ("1", "1", 30)],
)
async def test_extraction_produces_a_plausible_entry_count(
    article_number: str, comma_number: str, min_entries: int
) -> None:
    if not _live_run_requested():
        pytest.skip(
            "requires a real OPENROUTER_API_KEY AND GLOSSARY_SPIKE_LIVE=1, "
            "both set explicitly for this run"
        )

    real_key = os.environ["OPENROUTER_API_KEY"]
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
        agent_config, OpenRouterProvider(api_key=real_key), NullLlmCallTracker()
    )

    entries = []
    for _, chunk_text in split_into_chunks(block.text, max_chars=6000):
        response = await agent.run(GlossaryExtractorRequest(block_text=chunk_text))
        entries.extend(response.entries)

    assert len(entries) >= min_entries, [e.term for e in entries]
