from collections.abc import Iterable

from commons.ai.embedding.models import EmbeddingResult
from commons.ai.embedding.protocols import TextComposer
from commons.use_cases import UseCase

from .embedding_service import EmbeddingService


class ModelEmbeddingService[T](UseCase[Iterable[T], list[EmbeddingResult[T]]]):
    """Embeds a sequence of models, composing each one's text via an injected `TextComposer`.

    Synchronous: the rest of the stack (`EmbeddingClient`, `EmbeddingService`, `UseCase`) is
    synchronous, so introducing async here would require an unjustified bridge.

    Delegates all chunking/progress/retry to the injected `EmbeddingService`, avoiding any
    duplication of its already-tested batching logic.
    """

    def __init__(self, composer: TextComposer[T], embedding_service: EmbeddingService) -> None:
        """Injects the text composer and the embedding service.

        Args:
            composer: Turns a model of type `T` into the text to embed.
            embedding_service: Use case computing vectors for a batch of texts, invoked
                via `__call__`, not `.execute()` — see `.claude/rules/use-case-invocation.md`.
        """
        self._composer = composer
        self._embedding_service = embedding_service

    def execute(self, request: Iterable[T]) -> list[EmbeddingResult[T]]:
        """Composes and embeds every model, returning results aligned 1:1 to `request`."""
        models = list(request)
        texts = [self._composer.compose(model) for model in models]
        vectors = self._embedding_service(texts)
        return [
            EmbeddingResult(model=model, text=text, embedding=vector)
            for model, text, vector in zip(models, texts, vectors, strict=True)
        ]
