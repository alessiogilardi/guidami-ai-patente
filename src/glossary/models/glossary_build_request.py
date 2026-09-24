from pydantic import BaseModel, ConfigDict


class GlossaryBuildRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    force: bool
