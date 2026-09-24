"""Data-access layer for the standalone glossary package."""

from .glossary_agent_config_repository import GlossaryAgentConfigRepository
from .glossary_block_read_repository import GlossaryBlockReadRepository
from .glossary_entry_read_repository import GlossaryEntryReadRepository

__all__ = [
    "GlossaryAgentConfigRepository",
    "GlossaryBlockReadRepository",
    "GlossaryEntryReadRepository",
]
