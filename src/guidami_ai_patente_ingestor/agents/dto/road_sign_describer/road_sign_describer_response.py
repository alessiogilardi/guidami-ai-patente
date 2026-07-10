from pydantic import BaseModel


class RoadSignDescriberResponse(BaseModel):
    """Structured output of the road sign description agent.

    The field order encodes the Chain-of-Thought sequence enforced by
    pydantic-ai via `output_type`: the model reasons in writing in
    `visual_analysis` before synthesizing `name` and `description`.

    Attributes:
        visual_analysis: Internal visual reasoning (Chain-of-Thought) about
            the image content. Not persisted or included in
            `image_description`: it is discarded downstream by
            `RoadSignDescriberMapper`, which reads only `name` and `description`.
        name: Name of the road sign.
        description: Detailed description of the sign.
    """

    visual_analysis: str
    name: str
    description: str
