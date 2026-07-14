from pydantic import BaseModel, computed_field


class RoadSignDescriberRequest(BaseModel):
    """Input for the road sign description agent.

    Carries the contexts of every quiz that references a single image (the describer
    is called once per image). `contexts_block` renders the list into the bullet block
    consumed by the `$contexts_block` template variable; it is a `@computed_field` so
    `PromptRenderer.model_dump()` exposes it to `Template.safe_substitute`.

    Attributes:
        contexts: One entry per distinct quiz using the image (topic + text).
    """

    contexts: list[str]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def contexts_block(self) -> str:
        """Render `contexts` as a newline-separated bullet list for the prompt."""
        return "\n".join(f"- {c}" for c in self.contexts)
