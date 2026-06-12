from pathlib import Path

from pydantic import BaseModel, ConfigDict

from commons.configs import EmbeddingConfig, VectorStoreConfig


class IngestorConfig(BaseModel):
    """Configurazione della pipeline di indicizzazione (CdS + CAP)."""

    model_config = ConfigDict(frozen=True)

    cds_path: Path = Path("data/processed/cds/codice_della_strada.json")
    cap_path: Path = Path("data/processed/cap/codice_rca.json")
    embedding_batch_size: int = 64
    embedding: EmbeddingConfig = EmbeddingConfig()
    vector_store: VectorStoreConfig
