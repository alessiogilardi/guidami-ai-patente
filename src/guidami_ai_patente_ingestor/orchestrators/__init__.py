"""Orchestratori dell'ingestor."""

from .knowledge_flows import (
    build_knowledge_cleaning_flow,
    build_knowledge_enrichment_flow,
    build_knowledge_indexing_flow,
)
from .preparation_runner import run_preparation
from .quiz_flows import build_quiz_indexing_flow, build_quiz_preparation_flow

__all__ = [
    "build_knowledge_cleaning_flow",
    "build_knowledge_enrichment_flow",
    "build_knowledge_indexing_flow",
    "build_quiz_indexing_flow",
    "build_quiz_preparation_flow",
    "run_preparation",
]
