"""Input of the explanation writer: the question, the verdict, and the labeled commas."""

from pydantic import BaseModel, Field, computed_field

from guidami_ai_patente.models import LabeledComma

_NO_IMAGE_DESCRIPTION = "Nessuna immagine allegata a questa domanda."
_NO_SUBMITTED_ANSWER = "Non comunicata"


class ExplanationWriterRequest(BaseModel):
    """Everything the writer may speak about, and nothing else (FR-10).

    Request DTOs stay documented in English: their values are substituted into the
    user-prompt template, but their docstrings are never shipped to the model as
    schema — only `ExplanationWriterResponse`'s are.

    Attributes:
        quiz_text: Text of the quiz question.
        correct_answer: The stored correct answer.
        commas: The labeled commas, ordered by `judge_rank`. At least one: FR-7
            forbids invoking the writer without supporting commas, and the minimum
            makes that structural rather than a caller's responsibility.
        image_description: Description of the attached image, when the question has
            one.
        submitted_answer: What the user answered, when the client sent it (FR-11).
            `None` yields a neutral explanation.
    """

    quiz_text: str = Field(min_length=1)
    correct_answer: bool
    commas: list[LabeledComma] = Field(min_length=1)
    image_description: str | None = None
    submitted_answer: bool | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def correct_answer_it(self) -> str:
        """Renders `correct_answer` as the Italian "Vero"/"Falso" literal."""
        return "Vero" if self.correct_answer else "Falso"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def submitted_answer_it(self) -> str:
        """Renders `submitted_answer`, or says it was not communicated (FR-11)."""
        if self.submitted_answer is None:
            return _NO_SUBMITTED_ANSWER
        return "Vero" if self.submitted_answer else "Falso"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def image_description_it(self) -> str:
        """Renders the image description, or the Italian absent-image fallback.

        The fallback lives here rather than at the call site (where the judge's
        equivalent sits) so no caller can render `None` into the prompt.
        """
        return self.image_description or _NO_IMAGE_DESCRIPTION

    @computed_field  # type: ignore[prop-decorator]
    @property
    def commas_block(self) -> str:
        """Renders the commas as one numbered `[citation — article title] text` line.

        Numbering starts at 1, matching the ordinals
        `ExplanationWriterResponse.cited_comma_numbers` must reference, and the same
        shape the judge saw its candidates in.
        """
        return "\n".join(
            f"{index}. [{comma.citation} — {comma.article_title}] {comma.text}"
            for index, comma in enumerate(self.commas, start=1)
        )
