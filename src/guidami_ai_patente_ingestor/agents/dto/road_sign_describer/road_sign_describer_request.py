from pydantic import BaseModel


class RoadSignDescriberRequest(BaseModel):
    """Input for the road sign description agent.

    Attributes:
        topic: Topic of the quiz question (provides context for the description).
        text: Text of the quiz question (provides context for the description).
    """

    topic: str
    text: str
