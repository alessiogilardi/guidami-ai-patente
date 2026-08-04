"""Configuration identifying one `RunArtifactWriter` run."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class RunArtifactWriterConfig(BaseModel):
    """Identifies the run `RunArtifactWriter` reports on."""

    model_config = ConfigDict(frozen=True)

    logs_root: Path
    source: str
    toc_url: str
    output_path: Path
