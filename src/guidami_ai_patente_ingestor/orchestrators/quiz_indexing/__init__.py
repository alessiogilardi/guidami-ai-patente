"""Orchestrazione dell'indicizzazione del quiz bank nella tabella `quiz_questions`."""

from .quiz_indexing_pipeline import QuizIndexingPipeline
from .quiz_indexing_pipeline_builder import QuizIndexingPipelineBuilder

__all__ = ["QuizIndexingPipeline", "QuizIndexingPipelineBuilder"]
