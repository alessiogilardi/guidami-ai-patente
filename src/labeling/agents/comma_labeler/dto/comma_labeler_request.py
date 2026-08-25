from pydantic import BaseModel, Field, computed_field

from domain.models.retrieval import RetrievedComma


class CommaLabelerRequest(BaseModel):
    """Input for the agent labeling which candidate commas justify a quiz answer.

    Attributes:
        quiz_text: Text of the quiz question.
        correct_answer: Correct answer to the question.
        candidates: Candidate commas presented to the judge, already shuffled into
            their final presentation order.
        image_description: Description of the attached image (if present).
    """

    quiz_text: str = Field(min_length=1)
    correct_answer: bool
    candidates: list[RetrievedComma] = Field(min_length=1)
    image_description: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def correct_answer_it(self) -> str:
        """Render `correct_answer` as the Italian "Vero"/"Falso" literal used in the prompt."""
        return "Vero" if self.correct_answer else "Falso"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def candidates_block(self) -> str:
        """Render `candidates` as one numbered `[citation — article title] text` line.

        Numbering starts at 1, matching the ordinals `CommaLabelerResponse.comma_numbers`
        must reference. Emits no cosine distance, no text-rank score and no arm marker
        (FR-6): the ordinal, the citation, the article title and the comma text are all
        that appear.
        """
        return "\n".join(
            f"{index}. [{candidate.citation} — {candidate.article_title}] {candidate.text}"
            for index, candidate in enumerate(self.candidates, start=1)
        )
