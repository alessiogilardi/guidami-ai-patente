from pydantic import BaseModel


class ArticleContextualizerResponse(BaseModel):
    """Structured output of the contextualization agent.

    Attributes:
        contexts: Dictionary `{comma_index: context_text}` for each comma
            of the article. Keys are integers (comma indices starting from 0).
    """

    contexts: dict[int, str]
