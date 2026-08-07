"""Generic helpers of the ingestor, with no domain-specific logic."""

from .comma_repeal_detector import detect_comma_repeal, is_comma_repealed

__all__ = ["detect_comma_repeal", "is_comma_repealed"]
