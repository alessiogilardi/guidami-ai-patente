"""Orchestratori dell'ingestor."""

from .knowledge_flows import build_knowledge_indexing_flow
from .quiz_flows import build_quiz_indexing_flow

__all__ = ["build_knowledge_indexing_flow", "build_quiz_indexing_flow"]
