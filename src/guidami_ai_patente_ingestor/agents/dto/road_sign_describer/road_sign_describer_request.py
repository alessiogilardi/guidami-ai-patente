from collections.abc import Iterable

from pydantic import BaseModel, Field, computed_field

from .quiz_statement_model import QuizStatementModel


class QuizContextModel(BaseModel):
    """One topic and every distinct labeled quiz statement filed under it, for a single image.

    Attributes:
        topic: Quiz topic shared by every statement in `statements`.
        statements: Distinct quiz statements filed under `topic` for the described image,
            each carrying its correct answer.
    """

    topic: str
    statements: list[QuizStatementModel] = Field(default_factory=list)


class RoadSignDescriberRequest(BaseModel):
    """Input for the road sign description agent.

    Carries the contexts of every quiz that references a single image (the describer
    is called once per image), grouped by topic. `contexts_block` renders the groups
    into the `Argomento/Domande` block consumed by the `$contexts_block` template
    variable, each statement marked `(Vero)` or `(Falso)`; it is a `@computed_field` so
    `PromptRenderer.model_dump()` exposes it to `Template.safe_substitute`.

    Attributes:
        contexts: One entry per distinct topic, with every distinct labeled statement under it.
    """

    contexts: list[QuizContextModel]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def contexts_block(self) -> str:
        """Render `contexts` as one "Argomento/Domande" block per topic for the prompt."""
        return "\n\n".join(
            f"Argomento: {context.topic}\nDomande:\n{_make_dot_list(context.statements)}"
            for context in self.contexts
        )


def _make_dot_list(statements: Iterable[QuizStatementModel]) -> str:
    return "\n".join(f"- ({_answer_label(s)}) {s.text}" for s in statements)


def _answer_label(statement: QuizStatementModel) -> str:
    return "Vero" if statement.correct_answer else "Falso"
