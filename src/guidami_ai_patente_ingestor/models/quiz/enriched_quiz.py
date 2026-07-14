from pydantic import BaseModel

from .image_analysis import ImageAnalysis
from .quiz_metadata import QuizMetadata


class EnrichedQuizModel(BaseModel):
    """Enriched quiz bank sub-question, flattened.

    Carries `image_description` (flat, downstream) and `image_analysis` (full LLM
    output, debug-only).
    """

    question_id: int
    topic: str
    number: str
    text: str
    correct_answer: bool
    image: str | None = None
    image_description: str | None = None
    image_analysis: ImageAnalysis | None = None
    quiz_metadata: QuizMetadata | None = None
