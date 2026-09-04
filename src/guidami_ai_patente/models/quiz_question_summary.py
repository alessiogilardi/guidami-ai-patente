"""The question projection the propose and fetch endpoints serve."""

from pydantic import BaseModel, ConfigDict


class QuizQuestionSummary(BaseModel):
    """A quiz question as the client is allowed to see it (FR-1, FR-2).

    `correct_answer` is absent by construction, not filtered later: AD-3 makes that
    exclusion the only structural guarantee that grading happens server-side, and a
    field that exists on the model is one `model_dump()` away from the wire.

    `image_filename` is the stored name; the endpoint URL is built from it by
    `QuizProposalService`, so the client never has to know the path shape (AD-24).
    """

    model_config = ConfigDict(frozen=True)

    number: str
    topic: str
    text: str
    image_filename: str | None
