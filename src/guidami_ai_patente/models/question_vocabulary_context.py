"""Exactly the question data the vocabulary agent is allowed to see (AD-4)."""

from pydantic import BaseModel, ConfigDict


class QuestionVocabularyContext(BaseModel):
    """The question as the vocabulary stage receives it — answer-blind (FR-2).

    No `correct_answer` field exists on this class, structurally, not by convention
    (AD-4) — `test_question_explainer_request_has_no_answer_field` (Task 6) asserts the
    same about the agent's own request DTO built from this.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    image_description: str | None
    embedding: list[float] | None
