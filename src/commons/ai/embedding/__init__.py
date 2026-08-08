"""Embedding clients, service, composition layer, and config shared between ingestor and app."""

from .clients import EmbeddingClient, LiteLLMEmbeddingClient, SentenceTransformerEmbeddingClient
from .composition import CallableComposer, FieldSpecComposer, TemplateComposer
from .configs import EmbeddingClientConfig
from .models import EmbeddingResult, EmbeddingSpec, FieldSpec
from .protocols import OptionalTextComposer, TextComposer
from .services import EmbeddingService, ModelEmbeddingService

__all__ = [
    "CallableComposer",
    "EmbeddingClient",
    "EmbeddingClientConfig",
    "EmbeddingResult",
    "EmbeddingService",
    "EmbeddingSpec",
    "FieldSpec",
    "FieldSpecComposer",
    "LiteLLMEmbeddingClient",
    "ModelEmbeddingService",
    "OptionalTextComposer",
    "SentenceTransformerEmbeddingClient",
    "TemplateComposer",
    "TextComposer",
]
