import operator
from dataclasses import dataclass

from commons.ai.embedding.composition import CallableComposer


@dataclass
class _Article:
    title: str
    body: str

    @property
    def embedded_text(self) -> str:
        return f"{self.title}\n{self.body}"


def test_compose_delegates_to_a_property_via_attrgetter() -> None:
    composer = CallableComposer(operator.attrgetter("embedded_text"))
    article = _Article(title="Titolo", body="Corpo")

    text = composer.compose(article)

    assert text == "Titolo\nCorpo"


def test_compose_delegates_to_an_arbitrary_function() -> None:
    composer = CallableComposer(str.upper)

    text = composer.compose("hello")

    assert text == "HELLO"
