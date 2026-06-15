"""Orchestrazione della pulizia del corpus normativo (`data/parsed` -> `data/cleaned`)."""

from .cleaning_pipeline import CleaningPipeline
from .cleaning_pipeline_builder import CleaningPipelineBuilder

__all__ = ["CleaningPipeline", "CleaningPipelineBuilder"]
