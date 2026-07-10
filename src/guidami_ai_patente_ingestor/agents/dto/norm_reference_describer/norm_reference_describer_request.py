from pydantic import BaseModel, Field


class NormReferenceDescriberRequest(BaseModel):
    """Input for the agent generating norm metadata for a quiz question.

    Attributes:
        topic: Topic of the quiz question.
        text: Text of the quiz question.
        correct_answer: Correct answer to the question.
        image_description: Description of the attached image (if present).
    """

    topic: str = Field(min_length=1)
    text: str = Field(min_length=1)
    correct_answer: bool
    image_description: str | None = None
