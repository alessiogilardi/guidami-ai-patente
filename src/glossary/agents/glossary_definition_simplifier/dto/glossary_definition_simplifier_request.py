from pydantic import BaseModel, Field, computed_field


class DefinitionToSimplifyDto(BaseModel):
    """One Italian term/verbatim-definition pair awaiting a plain-language rewrite."""

    term: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class GlossaryDefinitionSimplifierRequest(BaseModel):
    """One batch of verbatim definitions awaiting a plain-language rewrite (FR-3)."""

    entries: list[DefinitionToSimplifyDto] = Field(min_length=1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entries_block(self) -> str:
        """Renders `entries` as a numbered `term: definition` list for the prompt template."""
        return "\n".join(
            f"{i}. {entry.term}: {entry.definition}"
            for i, entry in enumerate(self.entries, start=1)
        )
