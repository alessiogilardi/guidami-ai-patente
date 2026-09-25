from pydantic import BaseModel, Field, computed_field


class TermToTranslateDto(BaseModel):
    term: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class GlossaryTermTranslatorRequest(BaseModel):
    """One batch of Italian terms awaiting a Russian rendering (FR-4)."""

    entries: list[TermToTranslateDto] = Field(min_length=1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entries_block(self) -> str:
        return "\n".join(
            f"{i}. {entry.term}: {entry.definition}"
            for i, entry in enumerate(self.entries, start=1)
        )
