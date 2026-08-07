"""Retrieval-adjacent utilities.

Shared across the ingestor's evaluation harness and any future retrieval-serving code
(spec 0007 AD-1's stated future consumer).
"""

from .reciprocal_rank_fusion import reciprocal_rank_fusion

__all__ = ["reciprocal_rank_fusion"]
