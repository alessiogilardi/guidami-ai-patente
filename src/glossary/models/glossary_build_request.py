from pydantic import BaseModel, ConfigDict


class GlossaryBuildRequest(BaseModel):
    """`build-glossary`'s single input: whether to rebuild every block regardless of state."""

    model_config = ConfigDict(frozen=True)

    force: bool
