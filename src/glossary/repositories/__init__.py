"""Data-access layer for the standalone glossary package."""

from .glossary_agent_config_repository import GlossaryAgentConfigRepository
from .glossary_block_read_repository import GlossaryBlockReadRepository
from .glossary_definition_read_repository import GlossaryDefinitionReadRepository
from .glossary_entry_read_repository import GlossaryEntryReadRepository
from .glossary_entry_write_repository import GlossaryEntryWriteRepository
from .glossary_term_read_repository import GlossaryTermReadRepository
from .glossary_term_update_repository import GlossaryTermUpdateRepository

__all__ = [
    "GlossaryAgentConfigRepository",
    "GlossaryBlockReadRepository",
    "GlossaryDefinitionReadRepository",
    "GlossaryEntryReadRepository",
    "GlossaryEntryWriteRepository",
    "GlossaryTermReadRepository",
    "GlossaryTermUpdateRepository",
]
