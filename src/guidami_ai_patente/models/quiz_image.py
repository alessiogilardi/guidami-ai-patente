"""An authorised image, loaded and ready to serve."""

from pydantic import BaseModel, ConfigDict


class QuizImage(BaseModel):
    """The bytes of a quiz image and the media type to serve them under (FR-12)."""

    model_config = ConfigDict(frozen=True)

    content: bytes
    media_type: str
