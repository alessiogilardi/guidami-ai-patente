from pydantic import BaseModel, Field, computed_field


class TermToTranslateDto(BaseModel):
    """One Italian term/definition pair awaiting a Russian rendering."""

    term: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class GlossaryTermTranslatorRequest(BaseModel):
    """One batch of Italian terms awaiting a Russian rendering (FR-4)."""

    entries: list[TermToTranslateDto] = Field(min_length=1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entries_block(self) -> str:
        """Renders `entries` as a numbered `term: definition` list for the prompt template."""
        return "\n".join(
            f"{i}. {entry.term}: {entry.definition}"
            for i, entry in enumerate(self.entries, start=1)
        )
