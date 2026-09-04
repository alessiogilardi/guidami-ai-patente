"""Container-managed assembly of the live labeling stack (spec 0012, AD-16; D3)."""

from pywire import Autowired, provider

from commons.repositories.db import CorpusReadRepository, QuizReadRepository
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig
from labeling.configs import LabelingConfig
from labeling.repositories import GoldenSetWriteRepository
from labeling.services import CandidateSetService, QuestionLabelingService
from labeling.wiring import (
    build_candidate_set_service,
    build_comma_labeler_agent,
    build_corpus_repository,
    build_golden_set_repository,
    build_question_labeling_service,
    build_question_lexeme_service,
    build_quiz_repository,
)

from .labeling_stack_provider import LabelingStackProvider
from .llm_call_tracker_provider import LlmCallTrackerProvider
from .open_router_provider_component import OpenRouterProviderComponent


@provider
class LiveLabelingStackProvider:
    """Builds, once, everything the live cache fill needs (FR-6, FR-9).

    Every object here belongs to `commons/` or `labeling/`, is constructed manually by
    the ingestor and the batch harness, and therefore cannot carry a pywire decorator
    without pushing the container outside `src/guidami_ai_patente/` (ADR 0015). They
    are assembled through `labeling.wiring`'s builders — the same functions
    `label_main` calls — so the API and the batch build the same graph from the same
    configuration rather than two lookalikes (AD-12).

    Separate from `LabelingStackProvider`, which stays the judge's *identity* (the
    loaded prompt and the epoch it implies), for two reasons (D3). First, the FR-14
    startup diagnostic resolves its checker inside a deliberate
    `try/except Exception`; folding the agent and the model client into the same
    provider would turn a malformed prompt file or a bad credential into one warning
    about a diagnostic. Second, `ExplanationStatusService` reads the epoch on every
    `POST /check`, and that path must not construct an LLM graph it never calls. This
    deviates from AD-16's "two providers total" — recorded as an errata on the spec.

    The judge is built from `LabelingStackProvider.agent_config`, the *already loaded*
    prompt whose hash is the epoch's `prompt_version`: reloading the file here would
    reintroduce the divergence AD-22 exists to prevent.

    `Autowired[LlmCallTrackerProvider]` is not optional plumbing: it is the dependency
    edge that makes `Container.close()` drain the tracker's queue *before* closing the
    pool it writes through (reverse build order).
    """

    config: Autowired[AppConfig]
    labeling_config: Autowired[LabelingConfig]
    judge_identity: Autowired[LabelingStackProvider]
    postgres: Autowired[PostgresClientProvider]
    open_router: Autowired[OpenRouterProviderComponent]
    tracker_provider: Autowired[LlmCallTrackerProvider]

    def __init__(self) -> None:
        """Assembles the retrieval, judging and write collaborators over one pool."""
        client = self.postgres.client
        self.corpus: CorpusReadRepository = build_corpus_repository(
            self.config.articles_table, self.config.article_commas_table, client
        )
        self.quiz: QuizReadRepository = build_quiz_repository(
            self.config.quiz_questions_table,
            self.config.quiz_question_embeddings_table,
            self.config.quiz_images_table,
            client,
        )
        self.golden_set: GoldenSetWriteRepository = build_golden_set_repository(
            self.config.labeling_runs_table,
            self.config.quiz_labelings_table,
            self.config.quiz_comma_labels_table,
            client,
        )
        lexeme_service = build_question_lexeme_service(self.labeling_config, self.corpus)
        self.candidate_set: CandidateSetService = build_candidate_set_service(
            self.labeling_config, self.corpus, lexeme_service
        )
        judge = build_comma_labeler_agent(
            self.judge_identity.agent_config,
            self.open_router.provider,
            self.tracker_provider.tracker,
        )
        self.question_labeling: QuestionLabelingService = build_question_labeling_service(
            self.labeling_config,
            self.labeling_config.shuffle_seed,
            self.candidate_set,
            self.golden_set,
            judge,
        )
