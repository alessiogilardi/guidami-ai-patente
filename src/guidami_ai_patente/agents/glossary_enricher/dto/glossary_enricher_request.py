"""Input of the on-demand glossary enricher: the question and its grounding commas (FR-2)."""

from pydantic import BaseModel, Field, computed_field

from domain.models.retrieval import RetrievedComma

_NO_IMAGE_DESCRIPTION = "Nessuna immagine allegata a questa domanda."


class GlossaryEnricherRequest(BaseModel):
    """Everything the on-demand glossary agent may speak about, and nothing else (FR-2).

    Deliberately has no field derived from the answer — mirrors
    `QuestionExplainerRequest`'s own answer-blindness (a test asserts this).

    Attributes:
        text: The quiz question's own text, verbatim.
        image_description: Description of the attached image, when present.
        commas: Candidate commas from the live retrieval stack
            (`LiveLabelingStackProvider.candidate_set`), grounding the agent's
            definitions when relevant (FR-2, FR-3). May be empty when the question has
            no indexed embedding for the epoch's variant (FR-2) — the agent still runs,
            falling back to general knowledge for every term.
    """

    text: str = Field(min_length=1)
    image_description: str | None = None
    commas: list[RetrievedComma] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def image_description_it(self) -> str:
        """Renders the image description, or the Italian absent-image fallback."""
        return self.image_description or _NO_IMAGE_DESCRIPTION

    @computed_field  # type: ignore[prop-decorator]
    @property
    def commas_block(self) -> str:
        """Renders the candidate commas as one numbered citation-style line each."""
        return "\n".join(
            f"{index}. [{comma.source} art. {comma.article_number} comma {comma.comma_number}] "
            f"{comma.text}"
            for index, comma in enumerate(self.commas, start=1)
        )
