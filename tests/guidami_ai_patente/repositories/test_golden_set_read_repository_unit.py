"""GoldenSetReadRepository.find_current_labeling is a pure function of its two parameters.

Spec 0013, FR-3, AD-2 — no hidden state, no autowired epoch source.
"""

from dataclasses import dataclass, field

from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.repositories import GoldenSetReadRepository
from labeling.models import LabelingEpoch


@dataclass
class _FakePostgresClient:
    rows: list[tuple[object, ...]] = field(default_factory=list)
    queries: list[tuple[object, list[object]]] = field(default_factory=list)

    def fetch(self, query: object, params: list[object] | None = None) -> list[tuple[object, ...]]:
        self.queries.append((query, params or []))
        return self.rows


@dataclass
class _FakeProvider:
    client: _FakePostgresClient


def _make_epoch(**overrides: object) -> LabelingEpoch:
    defaults: dict[str, object] = {
        "judge_model": "openrouter/google/gemini-2.5-flash-lite",
        "prompt_version": "deadbeefdeadbeef",
        "candidate_variant": "topic_text",
        "dense_k": 50,
        "text_k": 50,
        "lexeme_fields": ("image_description", "text", "topic"),
    }
    defaults.update(overrides)
    return LabelingEpoch(**defaults)  # type: ignore[arg-type]


def _make_repository(client: _FakePostgresClient, config: AppConfig) -> GoldenSetReadRepository:
    """`object.__new__` sidesteps pywire's instrumented `__init__`.

    The class has no constructor body of its own, so setting the two fields is the whole
    of construction.
    """
    repository = object.__new__(GoldenSetReadRepository)
    repository.config = config  # type: ignore[assignment]
    repository.postgres = _FakeProvider(client)  # type: ignore[assignment]
    return repository


def test_the_same_epoch_and_number_always_query_with_the_same_parameters(
    app_config: AppConfig,
) -> None:
    client = _FakePostgresClient(rows=[])
    repository = _make_repository(client, app_config)
    epoch = _make_epoch()

    repository.find_current_labeling("0001", epoch)
    repository.find_current_labeling("0001", epoch)

    first_params, second_params = client.queries[0][1], client.queries[1][1]
    assert (
        first_params
        == second_params
        == [
            "0001",
            epoch.judge_model,
            epoch.prompt_version,
            epoch.candidate_variant,
            epoch.dense_k,
            epoch.text_k,
            list(epoch.lexeme_fields),
        ]
    ), "no hidden state: two calls with identical arguments must send identical parameters"


def test_a_different_epoch_changes_only_the_epoch_parameters(app_config: AppConfig) -> None:
    client = _FakePostgresClient(rows=[])
    repository = _make_repository(client, app_config)
    first_epoch = _make_epoch()
    second_epoch = _make_epoch(dense_k=99)

    repository.find_current_labeling("0001", first_epoch)
    repository.find_current_labeling("0001", second_epoch)

    _, first_params = client.queries[0]
    _, second_params = client.queries[1]
    assert first_params[0] == second_params[0] == "0001"
    assert first_params[4] == 50
    assert second_params[4] == 99


def test_no_rows_is_a_cache_miss(app_config: AppConfig) -> None:
    client = _FakePostgresClient(rows=[])
    repository = _make_repository(client, app_config)

    assert repository.find_current_labeling("0001", _make_epoch()) is None
