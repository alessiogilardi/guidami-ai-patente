"""Root configuration for the FastAPI service."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict

from commons.configs import BaseConfig, PostgresConnectionConfig


class AppConfig(BaseConfig):
    """Root settings for the guidami-ai-patente API service.

    Built once at the entry point (`main.py`) and registered on the pywire container
    as a single instance — never loaded inside routers or services, and never built
    twice in one process: `register_instance` refuses to displace an existing
    registration, so a second instance either raises `RegistrationError` or is left
    unused while the container keeps serving the first. (It is *not* silently absorbed
    by a singleton cache: since pywire 0.6.0 `register()` does not modify the class it
    registers, so `AppConfig(...)` is an ordinary call returning a fresh object.)

    Declares no `labeling` field: `LabelingConfig` is a `BaseSettings` in its own
    right, loaded and registered independently by `main.py` (spec 0013, FR-1). A
    consumer that needs the shared labeling epoch declares its own
    `labeling_config: Autowired[LabelingConfig]` rather than reading
    `self.config.labeling`.

    Public, non-secret fields default from `configs/app_config.yaml` (`BaseConfig`'s
    `YamlConfigSettingsSource`, same posture as `IngestorConfig`/`LabelingConfig`/
    `BotConfig`); `.env`/environment variables still take precedence and remain the
    only source for secrets (`postgres.user`/`postgres.password`) and for
    `agents_dir`, which stays defaultless everywhere on purpose (AD-22).
    """

    model_config = SettingsConfigDict(yaml_file="configs/app_config.yaml")

    host: str = "0.0.0.0"
    port: int = 8000
    postgres: PostgresConnectionConfig
    quiz_images_dir: Path = Path("data/quiz-images")
    agents_dir: Path = Field(
        validation_alias=AliasChoices("AGENTS_DIR", "agents_dir"),
        description=(
            "Directory holding the agent YAML files, for the API's own agents whose "
            "prompts enter no configuration epoch (today: explanation_writer.yaml). "
            "Declared separately from LabelingConfig.agents_dir, which resolves the "
            "epoch-controlled judge prompt, per ADR 0020's dual-directory shape; both "
            "alias AGENTS_DIR and are deliberately defaultless (AD-22)."
        ),
    )

    articles_table: str = "articles"
    article_commas_table: str = "article_commas"
    quiz_questions_table: str = "quiz_questions"
    quiz_question_embeddings_table: str = "quiz_question_embeddings"
    labeling_runs_table: str = "labeling_runs"
    quiz_labelings_table: str = "quiz_labelings"
    quiz_comma_labels_table: str = "quiz_comma_labels"
    quiz_images_table: str = "quiz_images"
    users_table: str = "users"
    quiz_answers_table: str = "quiz_answers"
    labeling_deadline_s: float = Field(
        default=25.0,
        gt=0.0,
        description=(
            "Wall-clock budget for POST /label's retrieval-plus-judge stage on a cache "
            "miss (spec 0017, AD-10). Deployment configuration, never judge identity: "
            "it is not on LabelingConfig and does not enter the epoch key. Enforced by "
            "LabelingService rather than by lowering comma_labeler.yaml's own timeout, "
            "which the batch shares and needs longer."
        ),
    )
    explanation_deadline_s: float = Field(
        default=20.0,
        gt=0.0,
        description=(
            "Wall-clock budget for GET /explanation, writer stage only (FR-13; spec "
            "0017 narrowed this from covering the judge too — that moved to "
            "labeling_deadline_s). Deployment configuration, never judge identity. "
            "Must cover up to _CITATION_ATTEMPTS=3 sequential ExplanationWriterAgent "
            "calls (explanation_service.py) plus pydantic-ai's own validation "
            "retries; no measured production latency data exists yet, so 20.0s gives "
            "headroom while staying under the original pre-split 25.0s combined "
            "budget — tune with real data once available."
        ),
    )
