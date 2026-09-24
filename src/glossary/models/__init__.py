"""Shapes used across the standalone glossary package."""

from .block_outcome import BlockOutcome
from .extracted_entry import ExtractedEntry
from .glossary_block import CommaSpan, GlossaryBlock
from .glossary_build_report import GlossaryBuildReport
from .glossary_build_request import GlossaryBuildRequest

__all__ = [
    "CommaSpan",
    "GlossaryBlock",
    "ExtractedEntry",
    "BlockOutcome",
    "GlossaryBuildRequest",
    "GlossaryBuildReport",
]
