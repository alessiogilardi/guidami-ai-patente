"""GlossaryRetrievalConfig.embedding_column — which glossary_entries vector column to read.

AD-4: a new embedding model is a new embedding_* column, chosen via config.
"""

from guidami_ai_patente.configs import GlossaryRetrievalConfig


def test_embedding_column_defaults_to_embedding_3_small() -> None:
    assert GlossaryRetrievalConfig().embedding_column == "embedding_3_small"


def test_embedding_column_is_configurable() -> None:
    config = GlossaryRetrievalConfig(embedding_column="embedding_ada_002")
    assert config.embedding_column == "embedding_ada_002"


def test_enabled_defaults_to_true() -> None:
    assert GlossaryRetrievalConfig().enabled is True


def test_enabled_is_configurable() -> None:
    config = GlossaryRetrievalConfig(enabled=False)
    assert config.enabled is False
