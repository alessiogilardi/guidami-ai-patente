from pydantic import BaseModel, Field, computed_field

from domain.models.retrieval import RetrievedComma


class RetrievalJudgeRequest(BaseModel):
    """Input for the agent judging whether retrieved commas justify a quiz answer.

    Attributes:
        quiz_text: Text of the quiz question.
        correct_answer: Correct answer to the question.
        commas: Top-k commas retrieved for this question by dense retrieval.
    """

    quiz_text: str = Field(min_length=1)
    correct_answer: bool
    commas: list[RetrievedComma] = Field(min_length=1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def correct_answer_it(self) -> str:
        """Render `correct_answer` as the Italian "Vero"/"Falso" literal used in the prompt."""
        return "Vero" if self.correct_answer else "Falso"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def commas_block(self) -> str:
        """Render `commas` as one `[citation — article title] text` line per comma.

        The article title is included alongside the citation so the judge can
        interpret an isolated comma in the context of what its article is about,
        not just its own text.
        """
        return "\n".join(
            f"[{comma.citation} — {comma.article_title}] {comma.text}" for comma in self.commas
        )
