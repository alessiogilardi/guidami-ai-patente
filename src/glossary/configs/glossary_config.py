from pathlib import Path

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import SettingsConfigDict

from commons.configs import BaseConfig, PostgresConnectionConfig


class GlossaryBlockConfig(BaseModel):
    """One definitions block to extract (FR-1).

    `comma_number` absent means every comma of `article_number` is concatenated into
    one block (none of the shipped blocks use this — see
    `GlossaryBlock.comma_number_at`, Task 3, for how a multi-comma block's entries are
    still individually attributed).
    """

    model_config = ConfigDict(frozen=True)

    source: str
    file: str
    article_number: str
    comma_number: str | None = None


_DEFAULT_BLOCKS: tuple[GlossaryBlockConfig, ...] = (
    GlossaryBlockConfig(
        source="cds", file="cds/codice_della_strada.json", article_number="2", comma_number="1"
    ),
    GlossaryBlockConfig(
        source="cds", file="cds/codice_della_strada.json", article_number="2", comma_number="3"
    ),
    GlossaryBlockConfig(
        source="cds", file="cds/codice_della_strada.json", article_number="2", comma_number="4"
    ),
    GlossaryBlockConfig(
        source="cds", file="cds/codice_della_strada.json", article_number="3", comma_number="1"
    ),
    GlossaryBlockConfig(
        source="cds", file="cds/codice_della_strada.json", article_number="151", comma_number="1"
    ),
    GlossaryBlockConfig(
        source="cds", file="cds/codice_della_strada.json", article_number="157", comma_number="1"
    ),
    GlossaryBlockConfig(
        source="cap",
        file="cap/codice_assicurazioni_private.json",
        article_number="1",
        comma_number="1",
    ),
)


class GlossaryConfig(BaseConfig):
    """Root settings for the standalone glossary package (AD-5).

    Not nested in `IngestorConfig` or `AppConfig`: `glossary` is a self-contained
    derived asset (Problem & Motivation, rejected shapes). `agents_dir` is a third
    `AGENTS_DIR` root (alongside `LabelingConfig`'s and `AppConfig`'s); this prompt
    enters no configuration epoch, so nothing depends on it matching the others, only
    on being set.
    """

    model_config = SettingsConfigDict(yaml_file="configs/glossary.yaml", env_file=None)

    postgres: PostgresConnectionConfig
    agents_dir: Path = Field(
        validation_alias=AliasChoices("AGENTS_DIR", "agents_dir"),
        description="Directory holding glossary_extractor.yaml and glossary_term_translator.ru.yaml.",
    )
    parsed_dir: Path = Path("data/parsed")
    project_root: Path = Path(".")
    blocks: tuple[GlossaryBlockConfig, ...] = _DEFAULT_BLOCKS
    max_block_chars: int = 6000
    translation_batch_size: int = 10
    embedding_batch_size: int = 16
    glossary_entries_table: str = "glossary_entries"
    embedding_column: str = Field(
        default="embedding_3_small",
        description=(
            "Which glossary_entries vector column build-glossary writes (AD-4: a new "
            "embedding model is a new embedding_* column, chosen here without a code "
            "change). Must match the app side's AppConfig.glossary.embedding_column "
            "for the app to read what this actually wrote."
        ),
    )

    @field_validator("max_block_chars", "translation_batch_size", "embedding_batch_size")
    @classmethod
    def _validate_positive(cls, value: int, info: object) -> int:
        if value < 1:
            raise ValueError(f"{info.field_name} must be >= 1, got {value}")  # type: ignore[attr-defined]
        return value
