from pydantic import BaseModel, ConfigDict

from .block_outcome import BlockOutcome


class GlossaryBuildReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcomes: tuple[BlockOutcome, ...]
