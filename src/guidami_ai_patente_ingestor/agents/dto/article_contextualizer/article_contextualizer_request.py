from pydantic import BaseModel, computed_field


class ArticleContextualizerRequest(BaseModel):
    """Input for the norm article contextualization agent.

    `paragraphs_block` renders `paragraphs` into a numbered list for the
    `$paragraphs_block` template variable; it is a `@computed_field` so
    `PromptRenderer.model_dump()` exposes it to `Template.safe_substitute`.

    Attributes:
        title: Article title.
        text: Article main text.
        paragraphs: Article commas, in order.
    """

    title: str
    text: str
    paragraphs: list[str]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def paragraphs_block(self) -> str:
        """Render `paragraphs` as a numbered list (e.g. "1. ...", "2. ...") for the prompt."""
        return "\n".join(f"{i + 1}. {p}" for i, p in enumerate(self.paragraphs))
