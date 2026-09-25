from pydantic import BaseModel, ConfigDict


class GlossaryDefinitionSimplificationRequest(BaseModel):
    """`simplify-glossary-definitions`'s single input: resimplify every row, not only missing ones."""

    model_config = ConfigDict(frozen=True)

    force: bool
