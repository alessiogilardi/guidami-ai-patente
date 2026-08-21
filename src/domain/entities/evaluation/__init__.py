"""Entities for the golden-set tables (`labeling_runs`, `quiz_labelings`, `quiz_comma_labels`)."""

from .labeling_run import LabelingRunEntity
from .quiz_comma_label import QuizCommaLabelEntity
from .quiz_labeling import QuizLabelingEntity

__all__ = ["LabelingRunEntity", "QuizCommaLabelEntity", "QuizLabelingEntity"]
