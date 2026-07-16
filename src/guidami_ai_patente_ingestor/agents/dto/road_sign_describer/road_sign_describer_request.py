from collections.abc import Iterable

from pydantic import BaseModel, Field, computed_field


class QuizContextModel(BaseModel):
    """One topic and every distinct quiz text filed under it, for a single image.

    Attributes:
        topic: Quiz topic shared by every text in `texts`.
        texts: Distinct quiz texts filed under `topic` for the described image.
    """

    topic: str
    texts: list[str] = Field(default_factory=list)


class RoadSignDescriberRequest(BaseModel):
    """Input for the road sign description agent.

    Carries the contexts of every quiz that references a single image (the describer
    is called once per image), grouped by topic. `contexts_block` renders the groups
    into the `Argomento/Domande` block consumed by the `$contexts_block` template
    variable; it is a `@computed_field` so `PromptRenderer.model_dump()` exposes it
    to `Template.safe_substitute`.

    Attributes:
        contexts: One entry per distinct topic, with every distinct quiz text under it.
    """

    contexts: list[QuizContextModel]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def contexts_block(self) -> str:
        """Render `contexts` as one "Argomento/Domande" block per topic for the prompt."""
        return "\n\n".join(
            f"Argomento: {context.topic}\nDomande:\n{_make_dot_list(context.texts)}"
            for context in self.contexts
        )


def _make_dot_list(texts: Iterable[str]) -> str:
    return "\n".join(f"- {t}" for t in texts)
