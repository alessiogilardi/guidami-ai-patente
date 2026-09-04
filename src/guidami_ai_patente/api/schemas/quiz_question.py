"""Response schema for the propose and fetch endpoints."""

from pydantic import BaseModel


class QuizQuestionResponse(BaseModel):
    """A quiz question as served to the client (FR-1, FR-2).

    Carries no `correct_answer`: excluding it is what makes grading genuinely
    server-side (AD-3). `image_url` is the ready-to-call path of the FR-12 endpoint,
    or `null` for a question with no image — the client never builds the path itself
    (AD-24).
    """

    number: str
    topic: str
    text: str
    image_url: str | None
