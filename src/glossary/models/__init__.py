"""Shapes used across the standalone glossary package."""

from .block_outcome import BlockOutcome
from .extracted_entry import ExtractedEntry
from .glossary_block import CommaSpan, GlossaryBlock
from .glossary_build_report import GlossaryBuildReport
from .glossary_build_request import GlossaryBuildRequest
from .glossary_definition_row import GlossaryDefinitionRow
from .glossary_definition_simplification_report import GlossaryDefinitionSimplificationReport
from .glossary_definition_simplification_request import GlossaryDefinitionSimplificationRequest
from .glossary_term_row import GlossaryTermRow
from .glossary_term_translation_report import GlossaryTermTranslationReport
from .glossary_term_translation_request import GlossaryTermTranslationRequest
from .simplified_definition import SimplifiedDefinition
from .translated_term import TranslatedTerm

__all__ = [
    "CommaSpan",
    "GlossaryBlock",
    "ExtractedEntry",
    "BlockOutcome",
    "GlossaryBuildRequest",
    "GlossaryBuildReport",
    "GlossaryDefinitionRow",
    "GlossaryDefinitionSimplificationReport",
    "GlossaryDefinitionSimplificationRequest",
    "GlossaryTermRow",
    "SimplifiedDefinition",
    "TranslatedTerm",
    "GlossaryTermTranslationRequest",
    "GlossaryTermTranslationReport",
]
