"""Generic, stateless helpers for the labeling run's provenance (FR-11)."""

from .run_provenance import corpus_commit, prompt_version

__all__ = ["corpus_commit", "prompt_version"]
