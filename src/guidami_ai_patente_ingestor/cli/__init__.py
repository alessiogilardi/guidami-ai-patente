"""Ingest CLI package (see `.claude/rules/cli-structure.md`).

Entry point `guidami_ai_patente_ingestor.cli:main` stays valid via this re-export.
"""

from .main import main

__all__ = ["main"]
